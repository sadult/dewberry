"""Configurations — manage Xray/V2Ray servers.

Acquire configs by Fetch (GitHub), Manual Import (configs.md beside the exe),
or Add (paste a share-link). Rows can be pinged, edited, activated and
deleted. The active configuration is what the VPN/TUN engine connects with.
No subscriptions — by design.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...core import configs as cfg_mod
from ...core.links import parse_links
from ...core.ping import tcp_ping_many
from ...utils import icons
from ..widgets.common import Badge, Card, CardHeader, muted, ping_color


class ConfigsPage(QWidget):
    _fetched = Signal(list, str)      # servers, error
    _pinged = Signal(dict)            # {server_id: ms}

    # Emitted whenever the stored server list / active server changes, so the
    # dashboard config picker can stay in sync.
    servers_changed = Signal()

    def __init__(self, conn, store, parent=None):
        super().__init__(parent)
        self.conn = conn
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

        header = QHBoxLayout()
        title = QLabel("Configurations")
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch()
        self.count_badge = Badge("database")
        header.addWidget(self.count_badge)
        root.addLayout(header)
        root.addWidget(muted(
            "Import Xray/V2Ray configurations, test latency and pick the "
            "active server. Subscriptions are intentionally not used."))

        # Toolbar wraps on narrow windows so buttons never overlap.
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.btn_fetch = self._btn("Fetch", "download", primary=True)
        self.btn_import = self._btn("Manual Import", "file-text")
        self.btn_add = self._btn("Add", "plus")
        self.btn_ping = self._btn("Ping", "activity")
        self.btn_active = self._btn("Set active", "check")
        self.btn_edit = self._btn("Edit", "edit")
        self.btn_delete = self._btn("Delete", "trash")
        self.btn_delete.setObjectName("Danger")
        self.btn_fetch.clicked.connect(self._fetch)
        self.btn_import.clicked.connect(self._import_md)
        self.btn_add.clicked.connect(self._add)
        self.btn_ping.clicked.connect(self._ping)
        self.btn_active.clicked.connect(self._activate_selected)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_delete.clicked.connect(self._delete)
        for b in (self.btn_fetch, self.btn_import, self.btn_add, self.btn_ping,
                  self.btn_active, self.btn_edit, self.btn_delete):
            toolbar.addWidget(b)
        toolbar.addStretch()
        root.addLayout(toolbar)

        card = Card()
        clay = QVBoxLayout(card)
        clay.setContentsMargins(16, 14, 16, 14)
        clay.setSpacing(10)
        head = CardHeader("server", "Servers", icons.ACCENT)
        self.hint = muted("Double-click a row or use \u201cSet active\u201d to "
                          "choose the config the VPN/TUN connects with.")
        head.add_trailing(self.hint)
        clay.addWidget(head)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Protocol", "Address", "Ping", "Active"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(240)
        self.table.doubleClicked.connect(lambda *_: self._activate_selected())
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        clay.addWidget(self.table)
        root.addWidget(card)

        self._fetched.connect(self._on_fetched)
        self._pinged.connect(self._on_pinged)
        self.refresh()

    # ------------------------------------------------------------ helpers
    def _btn(self, text, icon_name, primary=False):
        b = QPushButton(f"  {text}")
        b.setObjectName("Primary" if primary else "Ghost")
        b.setIcon(icons.icon(icon_name, "#FFFFFF" if primary else icons.MUTED, 16))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def refresh(self) -> None:
        servers = self.store.servers
        active_id = self.store.get("active_server_id")
        self.table.setRowCount(len(servers))
        for row, s in enumerate(servers):
            self._set(row, 0, s.get("remark", "config"))
            self._set(row, 1, (s.get("protocol") or "").upper())
            self._set(row, 2, f"{s.get('address', '')}:{s.get('port', '')}")
            ms = s.get("ping_ms")
            ping_item = QTableWidgetItem(f"{ms} ms" if ms else "\u2014")
            if ms:
                ping_item.setForeground(QColor(ping_color(ms)))
            self.table.setItem(row, 3, ping_item)
            is_active = s.get("id") == active_id
            act_item = QTableWidgetItem("\u25cf" if is_active else "")
            act_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if is_active:
                act_item.setForeground(QColor(icons.GOOD))
            self.table.setItem(row, 4, act_item)
        self.count_badge.set_value(f"{len(servers)} configs",
                                   "good" if servers else "off")
        self.servers_changed.emit()

    def _set(self, row, col, text):
        self.table.setItem(row, col, QTableWidgetItem(str(text)))

    def _selected_server(self):
        row = self.table.currentRow()
        servers = self.store.servers
        if 0 <= row < len(servers):
            return servers[row]
        return None

    # ------------------------------------------------------------ actions
    def _fetch(self) -> None:
        url, ok = QInputDialog.getText(
            self, "Fetch configurations",
            "GitHub repository / raw URL:", QLineEdit.EchoMode.Normal,
            self.store.get("fetch_url", ""))
        if not ok or not url.strip():
            return
        url = url.strip()
        self.store.set("fetch_url", url)
        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("  Fetching\u2026")

        def worker():
            try:
                servers = cfg_mod.fetch_from_github(url)
                self._fetched.emit(servers, "")
            except Exception as exc:
                self._fetched.emit([], str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _import_md(self) -> None:
        try:
            servers = cfg_mod.import_configs_md()
        except FileNotFoundError:
            QMessageBox.warning(
                self, "Manual Import",
                f"No configs.md found beside the app.\nExpected: "
                f"{cfg_mod.configs_md_path()}")
            return
        except Exception as exc:
            QMessageBox.warning(self, "Manual Import", str(exc))
            return
        self._on_fetched(servers, "")

    def _on_fetched(self, servers, error) -> None:
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("  Fetch")
        if error:
            QMessageBox.warning(self, "Fetch failed", error)
            return
        if not servers:
            QMessageBox.information(self, "No configurations",
                                    "No valid configurations were found.")
            return
        added = self.store.add_servers(servers)
        self.refresh()
        QMessageBox.information(
            self, "Import complete",
            f"Added {added} new configuration(s); "
            f"{len(servers) - added} duplicate(s) skipped.")

    def _add(self) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self, "Add configuration",
            "Paste one or more share-links "
            "(vless://, vmess://, trojan://, ss://):")
        if not ok or not text.strip():
            return
        try:
            servers = parse_links(text)
        except Exception as exc:
            QMessageBox.warning(self, "Add configuration", str(exc))
            return
        if not servers:
            QMessageBox.warning(self, "Add configuration",
                                "No valid share-link could be parsed.")
            return
        added = self.store.add_servers(servers)
        self.refresh()
        QMessageBox.information(
            self, "Add configuration",
            f"Added {added} new configuration(s).")

    def _edit(self) -> None:
        server = self._selected_server()
        if not server:
            QMessageBox.information(self, "Edit", "Select a configuration first.")
            return
        text, ok = QInputDialog.getText(
            self, "Edit name", "Configuration name:",
            QLineEdit.EchoMode.Normal, server.get("remark", ""))
        if ok and text.strip():
            self.store.update_server(server["id"], remark=text.strip())
            self.refresh()

    def _delete(self) -> None:
        server = self._selected_server()
        if not server:
            QMessageBox.information(self, "Delete", "Select a configuration first.")
            return
        if QMessageBox.question(
                self, "Delete configuration",
                f"Delete \u201c{server.get('remark')}\u201d?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.store.remove_servers([server["id"]])
            self.refresh()

    def _activate_selected(self) -> None:
        server = self._selected_server()
        if not server:
            QMessageBox.information(
                self, "Set active", "Select a configuration first.")
            return
        self.store.set("active_server_id", server["id"])
        self.refresh()

    def _ping(self) -> None:
        servers = list(self.store.servers)
        if not servers:
            QMessageBox.information(self, "Ping", "Add a configuration first.")
            return
        self.btn_ping.setEnabled(False)
        self.btn_ping.setText("  Pinging\u2026")

        def worker():
            results: dict[str, int] = {}

            def on_result(server_id, ms):
                if ms is not None:
                    results[server_id] = ms

            try:
                tcp_ping_many(servers, on_result)
            except Exception:
                pass
            self._pinged.emit(results)

        threading.Thread(target=worker, daemon=True).start()

    def _on_pinged(self, results: dict) -> None:
        self.btn_ping.setEnabled(True)
        self.btn_ping.setText("  Ping")
        for s in self.store.servers:
            if s["id"] in results:
                self.store.update_server(s["id"], ping_ms=results[s["id"]])
            else:
                self.store.update_server(s["id"], ping_ms=None)
        self.refresh()
        if not results:
            QMessageBox.information(
                self, "Ping",
                "No servers responded. Check your connection and try again.")
