"""Best-effort system & network telemetry for the dashboard.

Everything here degrades gracefully: on any error a field simply reads
"—" / "n/a" so the UI never blocks or crashes. Heavier lookups (public IP,
country) are cached and refreshed on a slow cadence by the caller.
"""
from __future__ import annotations

import socket
import sys

try:  # optional; requirements list it, but never hard-fail without it
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))
        return s.getsockname()[0]
    except OSError:
        return "—"
    finally:
        s.close()


def public_ip(timeout: float = 4.0) -> tuple[str, str]:
    """Return (public_ip, country_code). Requires network; safe if offline."""
    if requests is None:
        return "—", ""
    try:
        data = requests.get("https://ipapi.co/json/", timeout=timeout).json()
        return str(data.get("ip") or "—"), str(data.get("country_code") or "")
    except Exception:
        try:
            ip = requests.get("https://api.ipify.org", timeout=timeout).text
            return ip.strip() or "—", ""
        except Exception:
            return "—", ""


def dns_servers() -> str:
    """Primary system DNS resolver(s), platform-aware, best effort."""
    if sys.platform.startswith("win"):
        try:
            import subprocess
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-DnsClientServerAddress -AddressFamily IPv4)."
                 "ServerAddresses | Select-Object -First 2"],
                capture_output=True, text=True, timeout=6,
                creationflags=0x08000000,
            ).stdout
            servers = [ln.strip() for ln in out.splitlines() if ln.strip()]
            return ", ".join(servers[:2]) if servers else "—"
        except Exception:
            return "—"
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as fh:
            servers = [ln.split()[1] for ln in fh
                       if ln.startswith("nameserver")]
        return ", ".join(servers[:2]) if servers else "—"
    except Exception:
        return "—"


def active_interface() -> str:
    if psutil is None:
        return "—"
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        ip = local_ip()
        for name, nic_addrs in addrs.items():
            for a in nic_addrs:
                if a.family == socket.AF_INET and a.address == ip:
                    if stats.get(name) and stats[name].isup:
                        return name
        for name, st in stats.items():
            if st.isup and name.lower() not in ("lo", "loopback"):
                return name
    except Exception:
        pass
    return "—"


def cpu_percent() -> float:
    if psutil is None:
        return 0.0
    try:
        return float(psutil.cpu_percent(interval=None))
    except Exception:
        return 0.0


def memory_percent() -> float:
    if psutil is None:
        return 0.0
    try:
        return float(psutil.virtual_memory().percent)
    except Exception:
        return 0.0
