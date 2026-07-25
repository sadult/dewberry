"""TUN mode (full-device VPN) for Windows.

Follows the official xjasonlyu/tun2socks wiki for Windows, with one crucial
difference discovered in the field: routes added with plain `route add`
sometimes get bound to the wrong interface (Windows picks the interface by
gateway lookup, and the freshly-created Wintun adapter may not have finished
plumbing its static address yet). The reliable, documented way is
`netsh interface ipv4 add route <prefix> "<interface name>" <nexthop>` which
names the interface EXPLICITLY. We also wait until the static address is
actually visible on the adapter before touching the routing table.

Anti-routing-loop measures:
- every real IP of the proxy server is pinned to the physical gateway;
- ConnectionManager binds Xray's outbounds to the physical interface
  (sockopt.interface) so direct traffic can never re-enter the TUN;
- IPv6 default flow is also steered into the TUN (::/1 + 8000::/1) so
  dual-stack networks don't silently bypass the tunnel.
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import threading
import time

from ..utils.paths import tun2socks_path

CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0


def is_admin() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True,
                       creationflags=CREATE_NO_WINDOW)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _default_gateway() -> str | None:
    """Parse `route print 0.0.0.0` for the current default gateway."""
    _, out = _run(["route", "print", "0.0.0.0"])
    found = re.findall(
        r"0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", out)
    return found[0] if found else None


def default_interface() -> tuple[str | None, str | None]:
    """(interface alias, gateway IP) of the current IPv4 default route."""
    ps = ("$r = Get-NetRoute -DestinationPrefix '0.0.0.0/0' "
          "-AddressFamily IPv4 -ErrorAction SilentlyContinue | "
          "Sort-Object RouteMetric,ifMetric | Select-Object -First 1; "
          "if ($r) { $r.InterfaceAlias + '|' + $r.NextHop }")
    code, out = _run(["powershell", "-NoProfile", "-NonInteractive",
                      "-Command", ps])
    if code == 0 and "|" in out:
        alias, gw = out.strip().splitlines()[-1].split("|", 1)
        alias, gw = alias.strip(), gw.strip()
        if alias and re.match(r"^\d+\.\d+\.\d+\.\d+$", gw) and gw != "0.0.0.0":
            return alias, gw
    return None, _default_gateway()


def _resolve_all(host: str) -> list[str]:
    """All IPv4 addresses of the proxy server (already-an-IP included)."""
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
        return [host]
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET,
                                   socket.SOCK_STREAM)
        return sorted({info[4][0] for info in infos})
    except OSError:
        return []


def _adapter_exists(name: str) -> bool:
    _, out = _run(["netsh", "interface", "show", "interface"])
    return name.lower() in out.lower()


class TunManager:
    """Owns the tun2socks process, routes and adapter DNS while TUN is on."""

    def __init__(self, log=print):
        self.log = log
        self.proc: subprocess.Popen | None = None
        # (family, prefix, interface, nexthop|None) added via netsh
        self._routes: list[tuple[str, str, str, str | None]] = []
        self._name = "DewberryTun"
        self.physical_interface: str | None = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    # ------------------------------------------------------------ start
    def start(self, socks_port: int, server_address: str, settings: dict,
              extra_bypass: list[str] | None = None) -> None:
        if not sys.platform.startswith("win"):
            raise OSError("TUN mode is only implemented for Windows.")
        if not is_admin():
            raise PermissionError("admin")
        exe = tun2socks_path()
        if not exe.exists():
            raise FileNotFoundError("tun2socks")

        wanted = settings.get("tun_name", "DewberryTun")
        tun_addr = settings.get("tun_address", "192.168.123.1")

        iface, gateway = default_interface()
        self.physical_interface = iface
        if not gateway:
            raise RuntimeError("tun_no_gateway")
        server_ips = _resolve_all(server_address)
        # extra endpoints that must also bypass the tunnel (e.g. the SNI
        # engine's real CONNECT_IP when the proxy targets a local listener)
        for host in (extra_bypass or []):
            for ip in _resolve_all(host):
                if ip not in server_ips:
                    server_ips.append(ip)
        # never pin loopback to the physical route
        server_ips = [ip for ip in server_ips if not ip.startswith("127.")]
        self.log(f"[tun] physical interface: {iface or '?'} "
                 f"gateway: {gateway} bypass: {server_ips or '?'}")

        # 1) start tun2socks, trying every known device syntax
        adapter: str | None = None
        for device in (f"tun://{wanted}", f"wintun://{wanted}", "wintun"):
            name = wanted if "://" in device else "wintun"
            self.log(f"[tun] trying device syntax: {device}")
            if self._spawn(exe, device, socks_port) and self._wait_adapter(name):
                adapter = name
                break
            self._kill_proc()
        if adapter is None:
            raise RuntimeError("tun_adapter")
        self._name = adapter
        self.log(f"[tun] adapter '{adapter}' is up")

        # 2) static address + wait until Windows actually applied it
        self._cfg(["netsh", "interface", "ipv4", "set", "address",
                   f"name={self._name}", "source=static",
                   f"addr={tun_addr}", "mask=255.255.255.0"])
        if not self._wait_address(tun_addr):
            self.log("[tun] address not applied yet, retrying once")
            self._cfg(["netsh", "interface", "ipv4", "set", "address",
                       f"name={self._name}", "source=static",
                       f"addr={tun_addr}", "mask=255.255.255.0"])
            self._wait_address(tun_addr)

        # 3) metric + DNS on the adapter (per official wiki)
        self._cfg(["netsh", "interface", "ipv4", "set", "interface",
                   self._name, "metric=1"])
        self._cfg(["netsh", "interface", "ipv4", "set", "dnsservers",
                   f"name={self._name}", "static", "address=8.8.8.8",
                   "register=none", "validate=no"])
        self._cfg(["netsh", "interface", "ipv4", "add", "dnsservers",
                   f"name={self._name}", "address=1.1.1.1", "index=2",
                   "validate=no"])

        # 4) keep the proxy server itself on the physical route
        for ip in server_ips:
            if iface:
                self._add_route("ipv4", f"{ip}/32", iface, gateway)
            else:
                _run(["route", "add", ip, "mask", "255.255.255.255",
                      gateway, "metric", "1"])

        # 5) hijack the default route with the /1 pair, bound EXPLICITLY
        #    to the TUN adapter by name (this is the part `route add`
        #    kept getting wrong)
        ok1 = self._add_route("ipv4", "0.0.0.0/1", self._name, tun_addr)
        ok2 = self._add_route("ipv4", "128.0.0.0/1", self._name, tun_addr)
        if not (ok1 and ok2):
            self.stop()
            raise RuntimeError("tun_route")

        # 6) steer IPv6 into the TUN too (best effort; stops v6 bypass)
        self._add_route("ipv6", "::/1", self._name, None, required=False)
        self._add_route("ipv6", "8000::/1", self._name, None, required=False)

        _run(["ipconfig", "/flushdns"])
        if not self.running:
            self.stop()
            raise RuntimeError("tun2socks_exit")
        self.log(f"TUN up on {self._name} ({tun_addr}), gateway {gateway}")

    # ------------------------------------------------------------ helpers
    def _spawn(self, exe, device: str, socks_port: int) -> bool:
        """Start tun2socks; False if it dies immediately (bad syntax)."""
        self.proc = subprocess.Popen(
            [str(exe), "--device", device,
             "--proxy", f"socks5://127.0.0.1:{socks_port}",
             "--loglevel", "info"],
            cwd=str(exe.parent),  # so wintun.dll is found
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        threading.Thread(target=self._pump_logs, args=(self.proc,),
                         daemon=True).start()
        time.sleep(1.2)
        return self.running

    def _wait_adapter(self, name: str, timeout: float = 12.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.running:
                return False
            if _adapter_exists(name):
                return True
            time.sleep(0.25)
        return False

    def _wait_address(self, addr: str, timeout: float = 6.0) -> bool:
        """Wait until the static address is really live on the adapter."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _, out = _run(["netsh", "interface", "ipv4", "show",
                           "addresses", self._name])
            if addr in out:
                return True
            time.sleep(0.3)
        return False

    def _cfg(self, cmd: list[str]) -> None:
        code, out = _run(cmd)
        if code != 0:
            self.log(f"[tun] {' '.join(cmd[1:])} -> {out.strip()}")

    def _add_route(self, family: str, prefix: str, iface: str,
                   nexthop: str | None, required: bool = True) -> bool:
        cmd = ["netsh", "interface", family, "add", "route", prefix,
               f'interface={iface}']
        if nexthop:
            cmd.append(f"nexthop={nexthop}")
        cmd += ["metric=1", "store=active"]
        code, out = _run(cmd)
        if code != 0 and "exist" in out.lower():
            # stale route from a previous crash: replace it
            self._del_route(family, prefix, iface, nexthop)
            code, out = _run(cmd)
        ok = code == 0
        if ok:
            self._routes.append((family, prefix, iface, nexthop))
        elif required:
            self.log(f"[tun] add route {prefix} via {iface} -> {out.strip()}")
        return ok

    def _del_route(self, family: str, prefix: str, iface: str,
                   nexthop: str | None) -> None:
        cmd = ["netsh", "interface", family, "delete", "route", prefix,
               f"interface={iface}"]
        if nexthop:
            cmd.append(f"nexthop={nexthop}")
        _run(cmd)

    def _kill_proc(self) -> None:
        if self.proc:
            try:
                self.proc.kill()
                self.proc.wait(timeout=3)
            except Exception:
                pass
            self.proc = None

    def _pump_logs(self, proc: subprocess.Popen) -> None:
        if not proc.stdout:
            return
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.log(f"[tun2socks] {line}")
        except Exception:
            pass

    # ------------------------------------------------------------ stop
    def stop(self) -> None:
        for family, prefix, iface, nexthop in reversed(self._routes):
            self._del_route(family, prefix, iface, nexthop)
        self._routes.clear()
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None
        _run(["ipconfig", "/flushdns"])
        self.log("TUN down")
