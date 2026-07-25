"""Connection orchestrator: Xray core + Proxy Mode / TUN Mode."""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal

from .proxy import disable_system_proxy, enable_system_proxy
from .tun import TunManager
from .xray import XrayCore, _is_loopback

DISCONNECTED, CONNECTING, CONNECTED = "disconnected", "connecting", "connected"


class ConnectionManager(QObject):
    """Owns the live connection. Thread-safe via Qt queued signals."""

    state_changed = Signal(str)          # disconnected | connecting | connected
    log_line = Signal(str)
    error = Signal(str)                  # error code/message for the UI

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.state = DISCONNECTED
        self.current_server: dict | None = None
        self.connected_at: float | None = None
        self.core = XrayCore(log=self.log_line.emit)
        self.tun = TunManager(log=self.log_line.emit)
        self._proxy_set = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------ helpers
    def _set_state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit(state)

    def connect_server(self, server: dict | None = None) -> None:
        """Connect asynchronously (never blocks the UI thread)."""
        threading.Thread(target=self._connect_sync, args=(server,), daemon=True).start()

    def disconnect(self) -> None:
        threading.Thread(target=self._disconnect_sync, daemon=True).start()

    def toggle(self) -> None:
        if self.state == DISCONNECTED:
            self.connect_server()
        else:
            self.disconnect()

    # ------------------------------------------------------------ workers
    def _connect_sync(self, server: dict | None) -> None:
        with self._lock:
            server = server or self.store.active_server()
            if not server:
                self.error.emit("no_server")
                return
            if not self.core.available():
                self.error.emit("no_core")
                return
            self._teardown()
            self._set_state(CONNECTING)
            settings = self.store.settings
            try:
                mode = settings.get("mode", "proxy")
                bind_iface = None
                if mode == "tun":
                    from .tun import default_interface
                    bind_iface, _gw = default_interface()
                config = self.core.build_config(
                    server, settings, bind_interface=bind_iface)
                self.core.start(config)
                time.sleep(1.0)
                if not self.core.running:
                    raise RuntimeError("core_exit")

                if mode == "tun":
                    # With SNI chaining the proxy server address is the local
                    # Shade listener (127.0.0.1); the REAL remote endpoint is
                    # the SNI engine's CONNECT_IP. That endpoint must bypass
                    # the tunnel too, or the engine's upstream socket loops
                    # back through TUN.
                    extra_bypass = []
                    if _is_loopback(str(server.get("address", ""))):
                        try:
                            cip = str(self.store.sni.get(
                                "CONNECT_IP", "")).strip()
                            if cip:
                                extra_bypass.append(cip)
                        except Exception:
                            pass
                    self.tun.start(int(settings.get("socks_port", 10808)),
                                   server["address"], settings,
                                   extra_bypass=extra_bypass)
                else:
                    enable_system_proxy("127.0.0.1",
                                        int(settings.get("http_port", 10809)))
                    self._proxy_set = True

                self.current_server = server
                self.connected_at = time.time()
                self.store.set("active_server_id", server["id"])
                self._set_state(CONNECTED)
                self.log_line.emit(
                    f"Connected to {server.get('remark')} ({mode} mode)")
            except PermissionError:
                self._teardown()
                self._set_state(DISCONNECTED)
                self.error.emit("need_admin")
            except FileNotFoundError as exc:
                self._teardown()
                self._set_state(DISCONNECTED)
                self.error.emit("no_tun2socks" if "tun2socks" in str(exc) else "no_core")
            except Exception as exc:
                self._teardown()
                self._set_state(DISCONNECTED)
                self.error.emit(str(exc))

    def _disconnect_sync(self) -> None:
        with self._lock:
            self._teardown()
            self.current_server = None
            self.connected_at = None
            self._set_state(DISCONNECTED)
            self.log_line.emit("Disconnected")

    def _teardown(self) -> None:
        if self._proxy_set:
            try:
                disable_system_proxy()
            except Exception:
                pass
            self._proxy_set = False
        if self.tun.running:
            try:
                self.tun.stop()
            except Exception:
                pass
        self.core.stop()

    def shutdown(self) -> None:
        """Called on app exit: always leave the OS clean."""
        self._teardown()
