"""Integrated log console.

A single sink for engine logs, VPN/Xray logs, warnings, errors, connection
events and debug info. Features: colour-coded levels, live search/filter,
copy, clear and auto-scroll toggle. Kept intentionally flat and quiet.
"""
from __future__ import annotations

import re
import time
from collections import deque

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLineEdit,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from ...utils import icons

_LEVELS = {
    "error":   "#F87171",
    "warning": "#FBBF24",
    "warn":    "#FBBF24",
    "success": "#34D399",
    "info":    "#8FA0BD",
    "debug":   "#6C7690",
}
_SRC_TINT = {
    "[shade]": "#22D3EE",
    "[xray]":  "#8B5CF6",
    "[tun]":   "#60A5FA",
}


def _classify(line: str) -> str:
    low = line.lower()
    if any(k in low for k in ("error", "fail", "exception", "refused", "denied")):
        return "error"
    if any(k in low for k in ("warn", "retry", "timeout")):
        return "warning"
    if any(k in low for k in ("connected", "ready", "listening", "started", "success")):
        return "success"
    if "debug" in low:
        return "debug"
    return "info"


class Terminal(QWidget):
    """Colour-coded, searchable log console with a compact toolbar."""

    def __init__(self, buffer_size: int = 2000, parent=None):
        super().__init__(parent)
        self._buffer: deque[str] = deque(maxlen=buffer_size)
        self._filter = ""
        self._autoscroll = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter logs\u2026")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_filter)
        self.search.addAction(icons.icon("search", icons.MUTED, 15),
                              QLineEdit.ActionPosition.LeadingPosition)

        self.btn_autoscroll = QPushButton("Auto-scroll")
        self.btn_autoscroll.setObjectName("Ghost")
        self.btn_autoscroll.setCheckable(True)
        self.btn_autoscroll.setChecked(True)
        self.btn_autoscroll.setIcon(icons.icon("activity", icons.ACCENT_SOFT, 15))
        self.btn_autoscroll.toggled.connect(self._set_autoscroll)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.setObjectName("Ghost")
        self.btn_copy.setIcon(icons.icon("copy", icons.MUTED, 15))
        self.btn_copy.clicked.connect(self._copy)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("Ghost")
        self.btn_clear.setIcon(icons.icon("trash", icons.MUTED, 15))
        self.btn_clear.clicked.connect(self.clear)

        bar.addWidget(self.search, 1)
        bar.addWidget(self.btn_autoscroll)
        bar.addWidget(self.btn_copy)
        bar.addWidget(self.btn_clear)

        self.view = QPlainTextEdit()
        self.view.setObjectName("Terminal")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(buffer_size)
        self.view.setWordWrapMode(self.view.wordWrapMode().NoWrap
                                  if hasattr(self.view.wordWrapMode(), "NoWrap")
                                  else self.view.wordWrapMode())

        root.addLayout(bar)
        root.addWidget(self.view, 1)

    # ------------------------------------------------------------ logging
    def append(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        entry = f"{stamp}  {line}"
        self._buffer.append(entry)
        if self._passes(entry):
            self._render_line(entry)

    def _passes(self, entry: str) -> bool:
        return not self._filter or self._filter in entry.lower()

    def _render_line(self, entry: str) -> None:
        color = _LEVELS.get(_classify(entry), "#C8D2E4")
        for token, tint in _SRC_TINT.items():
            if token in entry:
                color = tint if _classify(entry) == "info" else color
                break
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self.view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(entry + "\n", fmt)
        if self._autoscroll:
            sb = self.view.verticalScrollBar()
            sb.setValue(sb.maximum())

    # ------------------------------------------------------------ controls
    def _on_filter(self, text: str) -> None:
        self._filter = text.strip().lower()
        self._rebuild()

    def _rebuild(self) -> None:
        self.view.clear()
        for entry in self._buffer:
            if self._passes(entry):
                self._render_line(entry)

    def _set_autoscroll(self, on: bool) -> None:
        self._autoscroll = on
        if on:
            sb = self.view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _copy(self) -> None:
        QApplication.clipboard().setText("\n".join(self._buffer))

    def clear(self) -> None:
        self._buffer.clear()
        self.view.clear()
