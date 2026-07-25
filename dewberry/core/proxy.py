"""Windows system proxy control (Proxy Mode).

Sets the WinINET proxy for the current user and notifies running apps.
The bypass list keeps Iranian domains and LAN traffic out of the proxy at
the OS level too (defence in depth next to Xray routing rules).
"""
from __future__ import annotations

import sys

DEFAULT_BYPASS = ";".join([
    "localhost", "127.*", "10.*", "172.16.*", "172.17.*", "172.18.*",
    "172.19.*", "172.2*", "172.30.*", "172.31.*", "192.168.*",
    "*.ir", "<local>",
])

_INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _refresh_wininet() -> None:
    import ctypes
    internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
    internet_set_option(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
    internet_set_option(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH


def enable_system_proxy(host: str, port: int, bypass: str = DEFAULT_BYPASS) -> None:
    if not sys.platform.startswith("win"):
        raise OSError("System proxy control is only implemented for Windows.")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS, 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
        winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, bypass)
    _refresh_wininet()


def disable_system_proxy() -> None:
    if not sys.platform.startswith("win"):
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS, 0,
                        winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
    _refresh_wininet()


def is_system_proxy_enabled() -> bool:
    if not sys.platform.startswith("win"):
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS) as key:
            value, _ = winreg.QueryValueEx(key, "ProxyEnable")
            return bool(value)
    except OSError:
        return False
