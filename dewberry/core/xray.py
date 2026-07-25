"""Xray-core process management and full client config generation."""
from __future__ import annotations

import json
import subprocess
import sys
import threading

from ..utils.paths import core_dir, data_dir, xray_path
from .links import to_outbound
from .routing import build_dns, build_routing

CREATE_NO_WINDOW = 0x08000000 if sys.platform.startswith("win") else 0


def _is_loopback(host: str) -> bool:
    """True for loopback / localhost addresses."""
    host = (host or "").strip().lower()
    return (host in ("127.0.0.1", "::1", "localhost")
            or host.startswith("127."))


class XrayCore:
    """Wraps the bundled xray(.exe): version checks, config build, run/stop."""

    def __init__(self, log=print):
        self.log = log
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None

    # ------------------------------------------------------------ info
    def available(self) -> bool:
        return xray_path().exists()

    def version(self) -> str:
        if not self.available():
            return ""
        try:
            out = subprocess.run(
                [str(xray_path()), "version"], capture_output=True, text=True,
                timeout=10, creationflags=CREATE_NO_WINDOW,
            ).stdout
            return out.splitlines()[0].strip() if out else ""
        except Exception:
            return ""

    # ------------------------------------------------------------ config
    def build_config(self, server: dict, settings: dict,
                     bind_interface: str | None = None) -> dict:
        """Full client config: SOCKS+HTTP inbounds, routing, DNS, stats API."""
        sniffing = {"enabled": True, "destOverride": ["http", "tls"],
                    "routeOnly": False}
        api_port = int(settings.get("api_port", 10853))
        inbounds = [
            {"tag": "socks-in", "listen": "127.0.0.1",
             "port": int(settings.get("socks_port", 10808)), "protocol": "socks",
             "settings": {"udp": True, "auth": "noauth"}, "sniffing": sniffing},
            {"tag": "http-in", "listen": "127.0.0.1",
             "port": int(settings.get("http_port", 10809)), "protocol": "http",
             "settings": {}, "sniffing": sniffing},
            {"tag": "api-in", "listen": "127.0.0.1", "port": api_port,
             "protocol": "dokodemo-door",
             "settings": {"address": "127.0.0.1"}},
        ]
        outbounds = [
            to_outbound(server, tag="proxy",
                        allow_insecure=settings.get("allow_insecure", False),
                        mux=settings.get("mux_enabled", False),
                        mux_concurrency=settings.get("mux_concurrency", 8)),
            {"tag": "direct", "protocol": "freedom", "settings": {}},
            {"tag": "block", "protocol": "blackhole",
             "settings": {"response": {"type": "http"}}},
        ]
        if bind_interface:
            # TUN mode: pin outbounds to the physical NIC so their packets
            # never re-enter the TUN adapter (routing loop). The DIRECT
            # outbound is always pinned. The PROXY outbound is pinned only
            # when it targets a real remote server; with SNI chaining it
            # targets the local Shade listener (127.0.0.1), and forcing a
            # loopback connection out the physical NIC yields the Windows
            # error "WSAEADDRNOTAVAIL / address not valid in its context".
            outbounds[1].setdefault("streamSettings", {}) \
                .setdefault("sockopt", {})["interface"] = bind_interface
            if not _is_loopback(str(server.get("address", ""))):
                outbounds[0].setdefault("streamSettings", {}) \
                    .setdefault("sockopt", {})["interface"] = bind_interface
        routing = build_routing(settings)
        routing.setdefault("rules", []).insert(0, {
            "type": "field", "inboundTag": ["api-in"], "outboundTag": "api"})
        return {
            "log": {"loglevel": settings.get("log_level", "warning")},
            "api": {"tag": "api", "services": ["StatsService"]},
            "stats": {},
            "dns": build_dns(settings),
            "inbounds": inbounds,
            "outbounds": outbounds,
            "routing": routing,
            "policy": {"system": {"statsOutboundUplink": True,
                                   "statsOutboundDownlink": True}},
        }

    # ------------------------------------------------------------ stats
    def query_stats(self, api_port: int) -> tuple[int, int]:
        """Return cumulative (uplink, downlink) bytes of the proxy outbound."""
        if not self.running:
            return 0, 0
        out = subprocess.run(
            [str(xray_path()), "api", "statsquery",
             f"--server=127.0.0.1:{api_port}"],
            capture_output=True, text=True, timeout=4,
            creationflags=CREATE_NO_WINDOW,
        ).stdout
        up = down = 0
        try:
            for stat in json.loads(out).get("stat", []):
                name = stat.get("name", "")
                value = int(stat.get("value", 0) or 0)
                if "outbound>>>proxy>>>" in name:
                    if name.endswith("uplink"):
                        up = value
                    elif name.endswith("downlink"):
                        down = value
        except (ValueError, AttributeError):
            pass
        return up, down

    # ------------------------------------------------------------ process
    def spawn(self, config: dict, name: str = "core") -> subprocess.Popen:
        """Start an extra xray instance (used for URL tests). Caller kills it."""
        path = data_dir() / f"{name}_config.json"
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return subprocess.Popen(
            [str(xray_path()), "run", "-c", str(path)],
            cwd=str(core_dir()),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )

    @staticmethod
    def kill(proc: subprocess.Popen | None) -> None:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def start(self, config: dict) -> None:
        if not self.available():
            raise FileNotFoundError("xray")
        self.stop()
        path = data_dir() / "current_config.json"
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        self.proc = subprocess.Popen(
            [str(xray_path()), "run", "-c", str(path)],
            cwd=str(core_dir()),  # so geoip.dat / geosite.dat are found
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
        )
        self._reader = threading.Thread(target=self._pump_logs, daemon=True)
        self._reader.start()

    def _pump_logs(self) -> None:
        proc = self.proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self.log(f"[xray] {line}")

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        self.kill(self.proc)
        self.proc = None
