"""Settings — all app preferences, grouped into unified cards.

Every control writes straight through to the Store on change. Grouped into:
Startup & behaviour, Connection & TUN, DNS, Networking & performance,
Logging and Updates.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ...utils import icons
from ..widgets.common import Card, CardHeader, caption
from ..widgets.toggle import Switch


class SettingsPage(QWidget):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Settings")
        title.setObjectName("H1")
        root.addWidget(title)

        root.addWidget(self._startup())
        root.addWidget(self._connection())
        root.addWidget(self._dns())
        root.addWidget(self._networking())
        root.addWidget(self._logging())
        root.addWidget(self._updates())
        root.addStretch()

    # ------------------------------------------------------------ helpers
    def _card(self, icon_name, title, tint=icons.ACCENT):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(CardHeader(icon_name, title, tint))
        return card, lay

    def _row(self, label, control, hint=""):
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(1)
        lb = QLabel(label)
        lb.setStyleSheet("color:#D4DBE8;font-weight:600;background:transparent;")
        col.addWidget(lb)
        if hint:
            col.addWidget(caption(hint))
        h.addLayout(col, 1)
        h.addWidget(control, 0, Qt.AlignmentFlag.AlignRight)
        return wrap

    def _switch(self, key, default=False):
        sw = Switch()
        sw.setChecked(bool(self.store.get(key, default)))
        sw.toggled.connect(lambda v, k=key: self.store.set(k, v))
        return sw

    def _combo(self, key, options, default):
        cb = QComboBox()
        cb.addItems(options)
        cur = str(self.store.get(key, default))
        if cur in options:
            cb.setCurrentText(cur)
        cb.setFixedWidth(150)
        cb.currentTextChanged.connect(lambda v, k=key: self.store.set(k, v))
        return cb

    def _spin(self, key, lo, hi, default):
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(int(self.store.get(key, default)))
        sp.setFixedWidth(120)
        sp.valueChanged.connect(lambda v, k=key: self.store.set(k, v))
        return sp

    def _line(self, key, default, width=180):
        le = QLineEdit(str(self.store.get(key, default)))
        le.setFixedWidth(width)
        le.editingFinished.connect(
            lambda k=key, w=le: self.store.set(k, w.text().strip()))
        return le

    # ------------------------------------------------------------ sections
    def _startup(self):
        card, lay = self._card("power", "Startup & behaviour", icons.ACCENT)
        lay.addWidget(self._row("Launch at login", self._switch("launch_at_login")))
        lay.addWidget(self._row("Start minimised", self._switch("start_minimized")))
        lay.addWidget(self._row("Close to tray", self._switch("close_to_tray", True)))
        lay.addWidget(self._row(
            "Auto-connect VPN on launch", self._switch("auto_connect"),
            "Connect to the last active configuration automatically."))
        lay.addWidget(self._row(
            "Auto-start SNI engine", self._switch("auto_start_sni"),
            "Enable the SNI spoofing engine on launch."))
        return card

    def _connection(self):
        card, lay = self._card("globe", "Connection & TUN", icons.ACCENT)
        lay.addWidget(self._row(
            "Routing mode", self._combo("mode", ["tun", "proxy"], "tun"),
            "TUN routes all traffic; proxy sets the system SOCKS/HTTP proxy."))
        lay.addWidget(self._row("SOCKS port", self._spin("socks_port", 1, 65535, 10808)))
        lay.addWidget(self._row("HTTP port", self._spin("http_port", 1, 65535, 10809)))
        lay.addWidget(self._row("TUN adapter address", self._line("tun_address", "192.168.123.1")))
        lay.addWidget(self._row("TUN adapter name", self._line("tun_name", "DewberryTun")))
        lay.addWidget(self._row("Bypass Iran routes", self._switch("bypass_iran", True)))
        lay.addWidget(self._row("Bypass LAN", self._switch("bypass_lan", True)))
        return card

    def _dns(self):
        card, lay = self._card("server", "DNS", icons.ACCENT_CYAN)
        lay.addWidget(self._row("Remote DNS", self._line("dns_remote", "8.8.8.8"),
                                "Resolver used for proxied domains."))
        lay.addWidget(self._row("Direct DNS", self._line("dns_iran", "78.157.42.100"),
                                "Resolver used for direct/bypassed domains."))
        return card

    def _networking(self):
        card, lay = self._card("activity", "Networking & performance", icons.ACCENT)
        lay.addWidget(self._row(
            "Allow insecure TLS", self._switch("allow_insecure"),
            "Skip certificate verification (not recommended)."))
        lay.addWidget(self._row("Enable Mux", self._switch("mux_enabled")))
        lay.addWidget(self._row("Mux concurrency", self._spin("mux_concurrency", 1, 128, 8)))
        lay.addWidget(self._row("Block ads", self._switch("block_ads", True)))
        lay.addWidget(self._row("Block malware", self._switch("block_malware", True)))
        lay.addWidget(self._row("Stats refresh (ms)", self._spin("stats_interval_ms", 250, 5000, 1000)))
        return card

    def _logging(self):
        card, lay = self._card("terminal", "Logging", icons.ACCENT_SOFT)
        lay.addWidget(self._row(
            "Core log level",
            self._combo("log_level", ["debug", "info", "warning", "error", "none"], "warning")))
        lay.addWidget(self._row("Log buffer (lines)", self._spin("log_buffer", 200, 20000, 2000)))
        lay.addWidget(self._row("Auto-scroll logs", self._switch("log_autoscroll", True)))
        return card

    def _updates(self):
        card, lay = self._card("refresh", "Updates", icons.ACCENT_HOT)
        lay.addWidget(self._row(
            "Check for updates", self._switch("check_updates", True),
            "Notify when a new Dewberry release is available."))
        return card
