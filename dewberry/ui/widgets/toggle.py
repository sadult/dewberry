"""Restrained connect control + iOS-style switch.

The :class:`ConnectButton` is a wide pill — not a flashy 3D disc. When active
it fills with the accent colour and emits a soft glow (the only glow in the
system besides live graphs). It animates a subtle press-scale on toggle and a
pulsing ring while connecting.
"""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, Qt,
                            Signal, QTimer)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton

from ...utils import icons

DISCONNECTED, CONNECTING, CONNECTED = "disconnected", "connecting", "connected"

_STATE_TINT = {
    DISCONNECTED: QColor("#7E8AA0"),
    CONNECTING: QColor("#60A5FA"),
    CONNECTED: QColor("#34D399"),
}


class ConnectButton(QAbstractButton):
    """Wide status-aware connect pill with a soft active glow."""

    toggled_state = Signal()

    def __init__(self, on_label="Connect", off_label="Disconnect", parent=None):
        super().__init__(parent)
        self._on_label = on_label
        self._off_label = off_label
        self._state = DISCONNECTED
        self._glow = 0.0
        self.setMinimumHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self.toggled_state.emit)

        self._anim = QPropertyAnimation(self, b"glow", self)
        self._anim.setDuration(900)
        self._anim.setStartValue(0.25)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)

        self._pulse = QTimer(self)
        self._pulse.timeout.connect(self.update)

    def get_glow(self):
        return self._glow

    def set_glow(self, v):
        self._glow = v
        self.update()

    glow = Property(float, get_glow, set_glow)

    def set_state(self, state: str) -> None:
        self._state = state
        if state == CONNECTING:
            self._anim.start()
        else:
            self._anim.stop()
            self._glow = 1.0 if state == CONNECTED else 0.0
        self.update()

    def _label(self) -> str:
        return {DISCONNECTED: self._on_label,
                CONNECTING: "Connecting\u2026",
                CONNECTED: self._off_label}[self._state]

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2
        tint = _STATE_TINT[self._state]

        # soft outer glow when active / connecting
        if self._state in (CONNECTED, CONNECTING):
            glow = QColor(tint)
            glow.setAlphaF(0.18 * self._glow)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(0, 0, w, h, r, r)
            inset = 3
        else:
            inset = 1

        rect = self.rect().adjusted(inset, inset, -inset, -inset)
        rr = rect.height() / 2
        if self._state == CONNECTED:
            p.setBrush(QColor("#12351F"))
            p.setPen(QPen(QColor("#34D399"), 1.4))
        elif self._state == CONNECTING:
            p.setBrush(QColor("#12203A"))
            p.setPen(QPen(QColor("#3B82F6"), 1.4))
        else:
            p.setBrush(QColor("#3B82F6"))
            p.setPen(QPen(QColor("#3B82F6"), 1.2))
        p.drawRoundedRect(rect, rr, rr)

        ink = QColor("#FFFFFF") if self._state == DISCONNECTED else tint
        p.setPen(ink)
        f = self.font()
        ps = f.pointSizeF()
        if ps <= 0:
            ps = 11.0
        f.setPointSizeF(ps + 0.5)
        f.setBold(True)
        p.setFont(f)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._label())


class Switch(QAbstractButton):
    """Compact iOS-style toggle used across Settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 26)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.toggled.connect(self._animate)

    def get_knob(self):
        return self._pos

    def set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def _animate(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        track_on = QColor("#3B82F6")
        track_off = QColor("#20293F")
        track = QColor(track_off)
        track = QColor(
            int(track_off.red() + (track_on.red() - track_off.red()) * self._pos),
            int(track_off.green() + (track_on.green() - track_off.green()) * self._pos),
            int(track_off.blue() + (track_on.blue() - track_off.blue()) * self._pos),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(0, 0, w, h, h / 2, h / 2)
        d = h - 6
        x = 3 + self._pos * (w - d - 6)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(int(x), 3, int(d), int(d))
