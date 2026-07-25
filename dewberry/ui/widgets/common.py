"""Shared design-system primitives for Dewberry.

Everything here enforces the unified system: one Card, one Badge, one
StatField, one section header, one set of typography helpers and formatters.
Elevation is deliberately minimal (a single low-opacity shadow) so the UI
reads as flat, calm and enterprise rather than glassy.
"""
from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QVBoxLayout, QWidget)

from ...utils import icons

# ---- radius / spacing tokens (kept in code for widgets that draw themselves)
RADIUS_CARD = 16
RADIUS_CTRL = 12
RADIUS_INPUT = 10


class Card(QFrame):
    """Flat surface with a subtle border and very restrained elevation."""

    def __init__(self, parent=None, elevated: bool = True):
        super().__init__(parent)
        self.setObjectName("Card")
        if elevated:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(24)
            shadow.setOffset(0, 6)
            shadow.setColor(QColor(0, 0, 0, 55))  # low opacity, no drama
            self.setGraphicsEffect(shadow)


class Inset(QFrame):
    """Recessed panel used inside cards (e.g. terminal, stat grids)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Inset")


# ------------------------------------------------------------ typography
def _label(text: str, name: str, wrap: bool = True) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def h1(text: str) -> QLabel:
    return _label(text, "H1")


def h2(text: str) -> QLabel:
    return _label(text, "H2")


def caption(text: str) -> QLabel:
    return _label(text, "Caption")


def muted(text: str) -> QLabel:
    return _label(text, "Muted")


def section_label(text: str) -> QLabel:
    return _label(text.upper(), "SectionLabel", wrap=False)


def page_layout(widget) -> QVBoxLayout:
    widget.setObjectName("Page")
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(26, 22, 26, 22)
    layout.setSpacing(14)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    return layout


class CardHeader(QWidget):
    """Standard card header: tinted icon tile + title + optional badge slot."""

    def __init__(self, icon_name: str, title: str, tint: str = icons.ACCENT,
                 parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(11)
        c = QColor(tint)
        tile = QLabel()
        tile.setFixedSize(34, 34)
        tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile.setStyleSheet(
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.14);"
            f"border: 1px solid rgba({c.red()},{c.green()},{c.blue()},0.28);"
            "border-radius: 10px;")
        tile.setPixmap(icons.pixmap(icon_name, tint, 17))
        self.title = QLabel(title)
        self.title.setObjectName("CardTitle")
        row.addWidget(tile)
        row.addWidget(self.title)
        row.addStretch()
        self._row = row

    def add_trailing(self, widget: QWidget) -> None:
        self._row.addWidget(widget)


class StatField(QWidget):
    """Compact key -> value row used throughout cards and the system panel."""

    def __init__(self, key: str, value: str = "\u2014", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self._key = QLabel(key)
        self._key.setObjectName("FieldKey")
        self._val = QLabel(value)
        self._val.setObjectName("FieldValue")
        self._val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self._key)
        row.addStretch()
        row.addWidget(self._val)

    def set_value(self, value: str) -> None:
        self._val.setText(value)

    def set_color(self, color: str | None) -> None:
        if color:
            self._val.setStyleSheet(f"color:{color};font-weight:600;background:transparent;")
        else:
            self._val.setStyleSheet("")
            self._val.setObjectName("FieldValue")


class Badge(QFrame):
    """Compact status pill: dot/icon + text, tinted by level.

    Levels map to the unified state system:
        good  -> Connected / Active / Success
        busy  -> Loading / Connecting
        mid   -> Warning
        bad   -> Error
        off   -> Disconnected / Disabled
    """

    COLORS = {"good": icons.GOOD, "busy": icons.ACCENT_SOFT, "mid": icons.WARN,
              "bad": icons.BAD, "off": icons.MUTED}

    def __init__(self, icon_name: str = "activity", parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.setObjectName("Badge")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 11, 4)
        row.setSpacing(6)
        self._icon = QLabel()
        self._text = QLabel()
        self._text.setObjectName("BadgeText")
        row.addWidget(self._icon)
        row.addWidget(self._text)
        self.set_value("\u2014", "off")

    def set_value(self, text: str, level: str) -> None:
        self._text.setText(text)
        color = self.COLORS.get(level, icons.MUTED)
        self._icon.setPixmap(icons.pixmap(self.icon_name, color, 13))
        for widget in (self, self._text):
            widget.setProperty("level", level)
            widget.style().unpolish(widget)
            widget.style().polish(widget)


# ------------------------------------------------------------ formatters
def fmt_bytes(n) -> str:
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "\u2014"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} PB"


def fmt_speed(bps) -> str:
    return f"{fmt_bytes(bps)}/s"


def fmt_duration(seconds) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "\u2014"
    if seconds < 0:
        return "\u2014"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def fmt_date(ts) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(int(ts)))
    except (TypeError, ValueError, OSError):
        return "\u2014"


def ping_color(ms) -> str:
    if ms is None:
        return icons.BAD
    if ms < 200:
        return icons.GOOD
    if ms < 600:
        return icons.WARN
    return "#FB923C"


def ping_level(ms) -> str:
    if ms is None:
        return "off"
    if ms < 200:
        return "good"
    if ms < 600:
        return "mid"
    return "bad"
