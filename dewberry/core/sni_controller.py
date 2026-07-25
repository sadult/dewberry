"""Qt-facing controller for the native Shade (SNI) engine.

Keeps the pure-networking :class:`SniEngine` free of any Qt dependency while
giving the UI thread-safe, signal-based state — mirroring the design of the
Xray/TUN ``ConnectionManager``.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from .sni_engine import (CONNECTED, CONNECTING, DISCONNECTED, SniEngine,
                         validate_sni_config)


class SniController(QObject):
    """Owns the Shade engine lifecycle and reports state via Qt signals."""

    state_changed = Signal(str)   # disconnected | connecting | connected
    log_line = Signal(str)
    error = Signal(str)

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.state = DISCONNECTED
        self.engine = SniEngine(log=self.log_line.emit)
        self._lock = threading.Lock()
        self._watch: threading.Thread | None = None

    # ------------------------------------------------------------ helpers
    def _set_state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit(state)

    def stats(self) -> dict:
        return self.engine.stats()

    # ------------------------------------------------------------ control
    def toggle(self) -> None:
        if self.state == DISCONNECTED:
            self.connect()
        else:
            self.disconnect()

    def connect(self) -> None:
        threading.Thread(target=self._connect_sync, daemon=True).start()

    def disconnect(self) -> None:
        threading.Thread(target=self._disconnect_sync, daemon=True).start()

    def _connect_sync(self) -> None:
        with self._lock:
            config = dict(self.store.sni)
            problems = validate_sni_config(config)
            if problems:
                self.error.emit("; ".join(problems))
                return
            self._set_state(CONNECTING)
            try:
                self.engine.start(config)
            except Exception as exc:
                self._set_state(DISCONNECTED)
                self.error.emit(str(exc))
                return
            # wait until the listener is actually bound (or the thread died)
            import time
            deadline = time.time() + 8
            while time.time() < deadline:
                if self.engine.ready:
                    self._set_state(CONNECTED)
                    self._start_watch()
                    return
                if not self.engine.running:
                    break
                time.sleep(0.1)
            self.engine.stop()
            self._set_state(DISCONNECTED)
            self.error.emit("sni_start_failed")

    def _disconnect_sync(self) -> None:
        with self._lock:
            try:
                self.engine.stop()
            except Exception:
                pass
            self._set_state(DISCONNECTED)

    def _start_watch(self) -> None:
        """Notice if the engine dies on its own and reflect it in the UI."""
        import time

        def _watch():
            while self.state == CONNECTED:
                if not self.engine.running:
                    self._set_state(DISCONNECTED)
                    self.error.emit("sni_stopped")
                    return
                time.sleep(1.0)

        self._watch = threading.Thread(target=_watch, daemon=True)
        self._watch.start()

    def shutdown(self) -> None:
        try:
            self.engine.stop()
        except Exception:
            pass
