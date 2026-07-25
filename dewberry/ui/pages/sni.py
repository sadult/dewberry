"""SNI Management — full control over the Shade engine configuration.

Every field is editable with inline validation. Supports Save, Restore
defaults, Import (from JSON) and Export (to JSON). Changes are blocked while
the engine is running so the live tunnel is never mutated underneath itself.
"""
from __future__ import annotations

import json

from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QVBoxLayout, QWidget)

from ...core.sni_engine import DEFAULT_SNI_CONFIG, validate_sni_config
from ...utils import icons
from ..widgets.common import (Badge, Card, CardHeader, caption, muted,
                             page_layout, section_label)

_FIELDS = [
    ("LISTEN_HOST", "Listen host", "IPv4 the local listener binds to (0.0.0.0 = all)."),
    ("LISTEN_PORT", "Listen port", "Local TCP port applications/TUN connect to."),
    ("FAKE_SNI", "Fake SNI", "Hostname sent in the forged TLS ClientHello."),
    ("CONNECT_IP", "Destination IP", "Real upstream IPv4 the tunnel connects to."),
    ("CONNECT_PORT", "Destination port", "Upstream TCP port (typically 443)."),
]


class SniPage(QWidget):
    def __init__(self, sni, store, parent=None):
        super().__init__(parent)
        self.sni = sni
        self.store = store
        self.inputs: dict[str, QLineEdit] = {}
        self.hints: dict[str, QLabel] = {}

        root = page_layout(self)
        header = QHBoxLayout()
        title = QLabel("SNI Management")
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch()
        self.state_badge = Badge("shield")
        header.addWidget(self.state_badge)
        root.addLayout(header)
        root.addWidget(muted(
            "Configure the native SNI-spoofing tunnel. Fields are locked while "
            "the engine is running."))

        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(14)
        lay.addWidget(CardHeader("sliders", "Engine configuration", icons.ACCENT_CYAN))

        form = QGridLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        form.setColumnStretch(1, 1)
        for r, (key, label, hint) in enumerate(_FIELDS):
            lb = QLabel(label)
            lb.setObjectName("FieldKey")
            edit = QLineEdit()
            edit.setPlaceholderText(str(DEFAULT_SNI_CONFIG[key]))
            edit.textChanged.connect(lambda _t, k=key: self._validate_field(k))
            hint_lb = caption(hint)
            self.inputs[key] = edit
            self.hints[key] = hint_lb
            form.addWidget(lb, r * 2, 0)
            form.addWidget(edit, r * 2, 1)
            form.addWidget(hint_lb, r * 2 + 1, 1)
        lay.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#F87171;background:transparent;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        lay.addWidget(self.error_label)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.btn_save = self._btn("Save", "save", primary=True)
        self.btn_reset = self._btn("Restore defaults", "refresh")
        self.btn_import = self._btn("Import", "download")
        self.btn_export = self._btn("Export", "upload")
        self.btn_save.clicked.connect(self._save)
        self.btn_reset.clicked.connect(self._restore_defaults)
        self.btn_import.clicked.connect(self._import)
        self.btn_export.clicked.connect(self._export)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_reset)
        buttons.addStretch()
        buttons.addWidget(self.btn_import)
        buttons.addWidget(self.btn_export)
        lay.addLayout(buttons)
        root.addWidget(card)
        root.addStretch()

        self.sni.state_changed.connect(self._on_state)
        self._load(self.store.sni)
        self._on_state(self.sni.state)

    # ------------------------------------------------------------ helpers
    def _btn(self, text, icon_name, primary=False):
        from PySide6.QtWidgets import QPushButton
        b = QPushButton(text)
        b.setObjectName("Primary" if primary else "Ghost")
        b.setIcon(icons.icon(icon_name, "#FFFFFF" if primary else icons.MUTED, 16))
        return b

    def _load(self, config: dict) -> None:
        for key, edit in self.inputs.items():
            edit.blockSignals(True)
            edit.setText(str(config.get(key, DEFAULT_SNI_CONFIG[key])))
            edit.blockSignals(False)
        self._validate_all()

    def _collect(self) -> dict:
        cfg = {}
        for key, edit in self.inputs.items():
            val = edit.text().strip()
            if key in ("LISTEN_PORT", "CONNECT_PORT"):
                try:
                    val = int(val)
                except ValueError:
                    pass
            cfg[key] = val
        return cfg

    def _validate_field(self, key: str) -> None:
        self._validate_all()

    def _validate_all(self) -> bool:
        errors = validate_sni_config(self._collect())
        blob = " ".join(errors).lower()
        for key, edit in self.inputs.items():
            bad = key.lower().replace("_", " ").split()[0] in blob or (
                key in ("LISTEN_PORT", "CONNECT_PORT") and "port" in blob) or (
                key == "FAKE_SNI" and "sni" in blob) or (
                key == "CONNECT_IP" and "destination ip" in blob) or (
                key == "LISTEN_HOST" and "listen host" in blob)
            edit.setProperty("invalid", "true" if bad and errors else "false")
            edit.style().unpolish(edit)
            edit.style().polish(edit)
        if errors:
            self.error_label.setText("  \u2022  ".join(errors))
            self.error_label.show()
            self.btn_save.setEnabled(False)
            return False
        self.error_label.hide()
        self.btn_save.setEnabled(self.sni.state == "disconnected")
        return True

    # ------------------------------------------------------------ actions
    def _save(self) -> None:
        if not self._validate_all():
            return
        self.store.set_sni(self._collect())
        QMessageBox.information(self, "SNI Management",
                                "Configuration saved.")

    def _restore_defaults(self) -> None:
        self._load(dict(DEFAULT_SNI_CONFIG))
        self.store.set_sni(dict(DEFAULT_SNI_CONFIG))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import SNI configuration", "", "JSON files (*.json)")
        if not path:
            return
        try:
            data = json.loads(open(path, encoding="utf-8").read())
            merged = dict(DEFAULT_SNI_CONFIG)
            merged.update({k: data[k] for k in DEFAULT_SNI_CONFIG if k in data})
            self._load(merged)
            if self._validate_all():
                self.store.set_sni(self._collect())
        except Exception as exc:
            QMessageBox.warning(self, "Import failed", str(exc))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SNI configuration", "sni_config.json",
            "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self._collect(), fh, indent=2)
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))

    def _on_state(self, state: str) -> None:
        running = state != "disconnected"
        label = {"disconnected": ("Stopped", "off"),
                 "connecting": ("Starting", "busy"),
                 "connected": ("Running", "good")}[state]
        self.state_badge.set_value(*label)
        for edit in self.inputs.values():
            edit.setEnabled(not running)
        self.btn_reset.setEnabled(not running)
        self.btn_import.setEnabled(not running)
        self.btn_save.setEnabled(not running and not self.error_label.isVisible())
