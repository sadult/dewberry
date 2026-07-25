"""Home — the Bento Grid dashboard.

A single glance surface: SNI control, VPN/TUN control, live network monitor,
system information and the integrated terminal, arranged in an enterprise
bento layout. The whole surface lives inside a scroll area so it stays usable
at small window sizes without any overlap. All values refresh on a 1s timer
driven by the main window.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QScrollArea, QVBoxLayout, QWidget)

from ...utils import icons
from ..widgets.common import (Badge, Card, CardHeader, StatField, caption,
                             fmt_bytes, fmt_duration, fmt_speed)
from ..widgets.toggle import ConnectButton
from ..widgets.traffic import DOWN_COLOR, UP_COLOR, StatChip, TrafficGraph

_STATE_BADGE = {
    "disconnected": ("Disconnected", "off", "power"),
    "connecting":   ("Connecting", "busy", "refresh"),
    "connected":    ("Connected", "good", "shield"),
}

_CARD_MIN_W = 300


def _card_body(card: Card, spacing: int = 12) -> QVBoxLayout:
    lay = QVBoxLayout(card)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(spacing)
    return lay


class HomePage(QWidget):
    def __init__(self, conn, sni, store, parent=None):
        super().__init__(parent)
        self.conn = conn        # ConnectionManager (Xray/TUN)
        self.sni = sni          # SniController (Shade engine)
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
        self._last_up = 0
        self._last_down = 0
        self._last_ts = None
        self.total_up = 0
        self.total_down = 0
        self._combo_sig = None
        self._combo_active = object()

        # ---- scrollable shell so nothing overlaps on small windows ----
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

        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch()
        self.overall = Badge("activity")
        self.overall.set_value("Idle", "off")
        header.addWidget(self.overall)
        root.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setContentsMargins(0, 0, 0, 0)
        root.addLayout(grid)

        grid.addWidget(self._build_sni_card(), 0, 0)
        grid.addWidget(self._build_vpn_card(), 0, 1)
        grid.addWidget(self._build_monitor_card(), 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # wire signals
        self.sni.state_changed.connect(self._on_sni_state)
        self.conn.state_changed.connect(self._on_vpn_state)
        self.btn_sni.toggled_state.connect(self.sni.toggle)
        self.btn_vpn.toggled_state.connect(self.conn.toggle)
        self._sync_server_combo()

    # ============================================================ SNI card
    def _build_sni_card(self) -> Card:
        card = Card()
        card.setMinimumWidth(_CARD_MIN_W)
        lay = _card_body(card)
        head = CardHeader("shield", "SNI Spoofing", icons.ACCENT_CYAN)
        self.sni_badge = Badge("power")
        head.add_trailing(self.sni_badge)
        lay.addWidget(head)

        self.f_sni_engine = StatField("Engine state", "Stopped")
        self.f_sni_runtime = StatField("Runtime", "\u2014")
        self.f_sni_listen = StatField("Listening on", "\u2014")
        self.f_sni_fake = StatField("Fake SNI", "\u2014")
        self.f_sni_dest = StatField("Destination", "\u2014")
        for f in (self.f_sni_engine, self.f_sni_runtime, self.f_sni_listen,
                  self.f_sni_fake, self.f_sni_dest):
            lay.addWidget(f)
        lay.addStretch()
        self.btn_sni = ConnectButton("Enable engine", "Disable engine")
        lay.addWidget(self.btn_sni)
        return card

    # ============================================================ VPN card
    def _build_vpn_card(self) -> Card:
        card = Card()
        card.setMinimumWidth(_CARD_MIN_W)
        lay = _card_body(card)
        head = CardHeader("globe", "VPN \u00b7 TUN Mode", icons.ACCENT)
        self.vpn_badge = Badge("power")
        head.add_trailing(self.vpn_badge)
        lay.addWidget(head)

        # --- config picker: choose which configuration TUN connects with ---
        lay.addWidget(caption("Configuration"))
        self.vpn_combo = QComboBox()
        self.vpn_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vpn_combo.currentIndexChanged.connect(self._on_config_picked)
        lay.addWidget(self.vpn_combo)

        self.f_vpn_server = StatField("Server", "\u2014")
        self.f_vpn_runtime = StatField("Runtime", "\u2014")
        self.f_vpn_ip = StatField("Public IP", "\u2014")
        self.f_vpn_country = StatField("Country", "\u2014")
        for f in (self.f_vpn_server, self.f_vpn_runtime,
                  self.f_vpn_ip, self.f_vpn_country):
            lay.addWidget(f)
        lay.addStretch()
        self.btn_vpn = ConnectButton("Connect", "Disconnect")
        lay.addWidget(self.btn_vpn)
        return card

    # ======================================================== monitor card
    def _build_monitor_card(self) -> Card:
        card = Card()
        card.setMinimumWidth(_CARD_MIN_W)
        lay = _card_body(card)
        head = CardHeader("activity", "Network Monitor", icons.ACCENT_CYAN)
        lay.addWidget(head)
        self.graph = TrafficGraph()
        lay.addWidget(self.graph)
        chips = QHBoxLayout()
        chips.setSpacing(12)
        self.chip_down = StatChip("arrow-down", DOWN_COLOR.name())
        self.chip_down.set_label("Download")
        self.chip_up = StatChip("arrow-up", UP_COLOR.name())
        self.chip_up.set_label("Upload")
        chips.addWidget(self.chip_down)
        chips.addWidget(self.chip_up)
        lay.addLayout(chips)
        return card

    # ==================================================== config picker
    def _on_config_picked(self, _index: int) -> None:
        sid = self.vpn_combo.currentData()
        if sid:
            self.store.set("active_server_id", sid)
            self._combo_active = sid

    def _sync_server_combo(self) -> None:
        """Repopulate the config picker only when the server list changes."""
        servers = self.store.servers
        active = self.store.get("active_server_id")
        sig = tuple((s["id"], s.get("remark"), s.get("ping_ms")) for s in servers)
        if sig == self._combo_sig and active == self._combo_active:
            self.vpn_combo.setEnabled(
                self.conn.state == "disconnected" and bool(servers))
            return
        self._combo_sig = sig
        self._combo_active = active
        self.vpn_combo.blockSignals(True)
        self.vpn_combo.clear()
        if not servers:
            self.vpn_combo.addItem("No configurations \u2014 add one first")
            self.vpn_combo.setEnabled(False)
        else:
            idx_active = 0
            for i, s in enumerate(servers):
                label = s.get("remark", "config")
                ms = s.get("ping_ms")
                if ms:
                    label += f"   \u00b7 {ms} ms"
                self.vpn_combo.addItem(label, s["id"])
                if s["id"] == active:
                    idx_active = i
            self.vpn_combo.setCurrentIndex(idx_active)
            self.vpn_combo.setEnabled(self.conn.state == "disconnected")
            if active is None:
                self.store.set("active_server_id", servers[idx_active]["id"])
                self._combo_active = servers[idx_active]["id"]
        self.vpn_combo.blockSignals(False)

    # ============================================================ signals
    def _on_sni_state(self, state: str) -> None:
        text, level, ic = _STATE_BADGE[state]
        self.sni_badge.set_value(text, level)
        self.btn_sni.set_state(state)
        self._refresh_overall()

    def _on_vpn_state(self, state: str) -> None:
        text, level, ic = _STATE_BADGE[state]
        self.vpn_badge.set_value(text, level)
        self.btn_vpn.set_state(state)
        self.vpn_combo.setEnabled(
            state == "disconnected" and bool(self.store.servers))
        self._refresh_overall()

    def _refresh_overall(self) -> None:
        s = self.sni.state == "connected"
        v = self.conn.state == "connected"
        if s and v:
            self.overall.set_value("Fully protected", "good")
        elif s or v:
            self.overall.set_value("Partially active", "busy")
        elif "connecting" in (self.sni.state, self.conn.state):
            self.overall.set_value("Connecting", "busy")
        else:
            self.overall.set_value("Idle", "off")

    # ============================================================ telemetry
    def set_network_info(self, pub_ip, country, local_ip, dns, iface):
        self._pub_ip, self._country = pub_ip, country
        self._local_ip, self._dns, self._iface = local_ip, dns, iface

    def set_resources(self, cpu, mem):
        self._cpu, self._mem = cpu, mem

    def set_latency(self, ms):
        self._latency = ms

    def tick(self) -> None:
        """Called ~1/s by the main window to refresh all live values."""
        self._sync_server_combo()
        self._tick_traffic()
        self._tick_sni()
        self._tick_vpn()

    def _tick_traffic(self) -> None:
        up_bps = down_bps = 0.0
        if self.conn.state == "connected":
            try:
                up, down = self.conn.core.query_stats(
                    int(self.store.get("api_port", 10853)))
            except Exception:
                up = down = 0
            now = time.time()
            if self._last_ts is not None:
                dt = max(0.001, now - self._last_ts)
                up_bps = max(0, (up - self._last_up)) / dt
                down_bps = max(0, (down - self._last_down)) / dt
            self._last_up, self._last_down, self._last_ts = up, down, now
            self.total_up, self.total_down = up, down
        else:
            self._last_ts = None
        self.graph.add_sample(up_bps, down_bps)
        self.chip_down.set_values(fmt_speed(down_bps), fmt_bytes(self.total_down))
        self.chip_up.set_values(fmt_speed(up_bps), fmt_bytes(self.total_up))

    def _tick_sni(self) -> None:
        st = self.sni.stats()
        running = st["running"] and st["ready"]
        self.f_sni_engine.set_value("Running" if running else
                                    ("Starting\u2026" if st["running"] else "Stopped"))
        self.f_sni_engine.set_color(icons.GOOD if running else None)
        self.f_sni_runtime.set_value(fmt_duration(st["uptime"]) if st["running"] else "\u2014")
        self.f_sni_listen.set_value(st["listen"] or "\u2014")
        self.f_sni_fake.set_value(st["fake_sni"] or "\u2014")
        self.f_sni_dest.set_value(
            f"{st['connect_ip']}:{st['connect_port']}"
            if st["connect_ip"] else "\u2014")

    def _tick_vpn(self) -> None:
        server = self.conn.current_server
        connected = self.conn.state == "connected"
        self.f_vpn_server.set_value(
            f"{server.get('address')}:{server.get('port')}" if server else "\u2014")
        if connected and self.conn.connected_at:
            self.f_vpn_runtime.set_value(fmt_duration(time.time() - self.conn.connected_at))
        else:
            self.f_vpn_runtime.set_value("\u2014")
        self.f_vpn_ip.set_value(self._pub_ip if connected else "\u2014")
        self.f_vpn_country.set_value(self._country or "\u2014" if connected else "\u2014")
