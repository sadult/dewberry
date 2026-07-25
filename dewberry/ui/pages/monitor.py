"""Monitor — detailed system information and the live log console.

These two panels used to crowd the Bento dashboard; they now live on their own
tab. The page owns the terminal and receives live values (network, resources,
latency) pushed from the main window, refreshing on the same 1s timer.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QScrollArea, QVBoxLayout,
                               QWidget)

from ...utils import icons
from ..widgets.common import Badge, Card, CardHeader, StatField, fmt_duration
from ..widgets.terminal import Terminal


def _card_body(card: Card, spacing: int = 12) -> QVBoxLayout:
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(spacing)
    return lay


class MonitorPage(QWidget):
    def __init__(self, conn, sni, store, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.sni = sni
        self.store = store
        self._pub_ip = "\u2014"
        self._country = ""
        self._local_ip = "\u2014"
        self._dns = "\u2014"
        self._iface = "\u2014"
        self._cpu = 0.0
        self._mem = 0.0
        self._latency = None
        self._app_started = time.time()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        body.setObjectName("Page")
        root = QVBoxLayout(body)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)

        header = QHBoxLayout()
        title = QLabel("Monitor")
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch()
        self.log_badge = Badge("terminal")
        self.log_badge.set_value("Live logs", "busy")
        header.addWidget(self.log_badge)
        root.addLayout(header)

        root.addWidget(self._build_system_card())
        root.addWidget(self._build_terminal_card(), 1)

        # logs stream here now (moved off the dashboard)
        self.sni.log_line.connect(self.terminal.append)
        self.conn.log_line.connect(self.terminal.append)
        self.sni.error.connect(lambda m: self.terminal.append(f"[shade] error: {m}"))
        self.conn.error.connect(lambda m: self.terminal.append(f"[vpn] error: {m}"))

    # ======================================================== system card
    def _build_system_card(self) -> Card:
        card = Card()
        lay = _card_body(card, spacing=7)
        lay.addWidget(CardHeader("cpu", "System information", icons.ACCENT_HOT))
        self.sys_fields: dict[str, StatField] = {}
        specs = [
            ("public_ip", "Public IP"), ("local_ip", "Local IP"),
            ("dns", "DNS"), ("iface", "Interface"),
            ("routing", "Routing mode"), ("tun", "TUN"),
            ("sni", "SNI"), ("xray", "Xray"),
            ("latency", "Latency"), ("cpu", "CPU"),
            ("mem", "Memory"), ("uptime", "App uptime"),
            ("versions", "Version"),
        ]
        grid_wrap = QVBoxLayout()
        grid_wrap.setSpacing(7)
        for key, label in specs:
            f = StatField(label)
            self.sys_fields[key] = f
            lay.addWidget(f)
        lay.addLayout(grid_wrap)
        return card

    # ====================================================== terminal card
    def _build_terminal_card(self) -> Card:
        card = Card()
        card.setMinimumHeight(320)
        lay = _card_body(card)
        lay.addWidget(CardHeader("terminal", "Logs", icons.ACCENT_SOFT))
        self.terminal = Terminal(
            buffer_size=int(self.store.get("log_buffer", 2000)))
        self.terminal.setMinimumHeight(240)
        lay.addWidget(self.terminal, 1)
        return card

    # ============================================================ telemetry
    def set_network_info(self, pub_ip, country, local_ip, dns, iface):
        self._pub_ip, self._country = pub_ip, country
        self._local_ip, self._dns, self._iface = local_ip, dns, iface

    def set_resources(self, cpu, mem):
        self._cpu, self._mem = cpu, mem

    def set_latency(self, ms):
        self._latency = ms

    def tick(self) -> None:
        from ...version import APP_VERSION, ENGINE_VERSION
        f = self.sys_fields
        f["public_ip"].set_value(self._pub_ip)
        f["local_ip"].set_value(self._local_ip)
        f["dns"].set_value(self._dns)
        f["iface"].set_value(self._iface)
        f["routing"].set_value(self.store.get("mode", "tun").upper())
        tun_on = self.conn.state == "connected" and self.store.get("mode") == "tun"
        f["tun"].set_value("Active" if tun_on else "Inactive")
        f["tun"].set_color(icons.GOOD if tun_on else None)
        sni_on = self.sni.state == "connected"
        f["sni"].set_value("Active" if sni_on else "Inactive")
        f["sni"].set_color(icons.ACCENT_CYAN if sni_on else None)
        xray_on = self.conn.core.running
        f["xray"].set_value("Running" if xray_on else "Stopped")
        f["xray"].set_color(icons.GOOD if xray_on else None)
        f["latency"].set_value(
            f"{self._latency} ms" if self._latency is not None else "\u2014")
        f["cpu"].set_value(f"{self._cpu:.0f}%")
        f["mem"].set_value(f"{self._mem:.0f}%")
        f["uptime"].set_value(fmt_duration(time.time() - self._app_started))
        f["versions"].set_value(f"app {APP_VERSION} \u00b7 engine {ENGINE_VERSION}")
