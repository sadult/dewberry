"""JSON persistence for Dewberry.

Holds three things in one atomic document:
  * settings       — app-wide preferences (appearance, TUN, DNS, SNI, ...)
  * servers        — the Xray/V2Ray configurations managed on the Configs page
  * sni            — the Shade (SNI spoofing) engine configuration

Subscriptions are intentionally NOT part of Dewberry.
"""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from typing import Any, Optional

from ..core.sni_engine import DEFAULT_SNI_CONFIG
from ..utils.paths import data_dir
from ..version import DEFAULT_FETCH_URL, URL_TEST_DEFAULT

DEFAULT_SETTINGS: dict[str, Any] = {
    # ---- appearance ----
    "theme": "midnight",              # midnight | navy | black
    "accent": "blue",                # blue | cyan | violet
    "reduce_motion": False,
    # ---- connection ----
    "mode": "tun",                   # "proxy" | "tun"
    "socks_port": 10808,
    "http_port": 10809,
    "api_port": 10853,
    "active_server_id": None,
    # ---- startup / behaviour ----
    "auto_connect": False,
    "auto_start_sni": False,
    "start_minimized": False,
    "launch_at_login": False,
    "close_to_tray": True,
    # ---- routing ----
    "bypass_iran": True,
    "bypass_lan": True,
    "block_ads": True,
    "block_malware": True,
    "custom_direct": [],
    "custom_proxy": [],
    "custom_block": [],
    # ---- dns ----
    "dns_remote": "8.8.8.8",
    "dns_iran": "78.157.42.100",
    # ---- tun ----
    "tun_address": "192.168.123.1",
    "tun_name": "DewberryTun",
    # ---- networking / performance ----
    "allow_insecure": False,
    "mux_enabled": False,
    "mux_concurrency": 8,
    "url_test": URL_TEST_DEFAULT,
    "stats_interval_ms": 1000,
    # ---- logging ----
    "log_level": "warning",          # xray core log level
    "log_buffer": 2000,              # max lines kept in the terminal panel
    "log_autoscroll": True,
    # ---- updates ----
    "check_updates": True,
    # ---- configurations ----
    "fetch_url": DEFAULT_FETCH_URL,
}


class Store:
    """Thread-safe app state persisted as one JSON document."""

    def __init__(self, path=None):
        self.path = path or (data_dir() / "dewberry.json")
        self._lock = threading.RLock()
        self.data: dict[str, Any] = {
            "settings": deepcopy(DEFAULT_SETTINGS),
            "servers": [],
            "sni": deepcopy(DEFAULT_SNI_CONFIG),
        }
        self.load()

    # ---------------- persistence ----------------
    def load(self) -> None:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                settings = deepcopy(DEFAULT_SETTINGS)
                settings.update(raw.get("settings", {}))
                sni = deepcopy(DEFAULT_SNI_CONFIG)
                sni.update(raw.get("sni", {}))
                self.data = {
                    "settings": settings,
                    "servers": raw.get("servers", []),
                    "sni": sni,
                }
            except (OSError, ValueError):
                pass  # first run / corrupt file -> defaults

    def save(self) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(self.path)

    # ---------------- settings ----------------
    @property
    def settings(self) -> dict[str, Any]:
        return self.data["settings"]

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

    def set(self, key: str, value) -> None:
        with self._lock:
            self.settings[key] = value
            self.save()

    def update_settings(self, patch: dict) -> None:
        with self._lock:
            self.settings.update(patch)
            self.save()

    # ---------------- sni config ----------------
    @property
    def sni(self) -> dict[str, Any]:
        return self.data["sni"]

    def set_sni(self, config: dict) -> None:
        with self._lock:
            self.data["sni"] = dict(config)
            self.save()

    def reset_sni(self) -> dict:
        self.set_sni(deepcopy(DEFAULT_SNI_CONFIG))
        return self.data["sni"]

    # ---------------- servers (Xray configs) ----------------
    @property
    def servers(self) -> list[dict]:
        return self.data["servers"]

    def get_server(self, server_id: Optional[str]) -> Optional[dict]:
        for s in self.servers:
            if s.get("id") == server_id:
                return s
        return None

    def active_server(self) -> Optional[dict]:
        return self.get_server(self.get("active_server_id"))

    def add_servers(self, servers: list[dict]) -> int:
        with self._lock:
            existing = {s.get("raw") for s in self.servers if s.get("raw")}
            added = 0
            for s in servers:
                if s.get("raw") and s.get("raw") in existing:
                    continue
                self.servers.append(s)
                existing.add(s.get("raw"))
                added += 1
            self.save()
            return added

    def add_server(self, server: dict) -> None:
        with self._lock:
            self.servers.append(server)
            self.save()

    def update_server(self, server_id: str, **patch) -> None:
        with self._lock:
            s = self.get_server(server_id)
            if s:
                s.update(patch)
                self.save()

    def remove_servers(self, ids: list[str]) -> None:
        with self._lock:
            self.data["servers"] = [s for s in self.servers
                                    if s["id"] not in ids]
            if self.get("active_server_id") in ids:
                self.settings["active_server_id"] = None
            self.save()
