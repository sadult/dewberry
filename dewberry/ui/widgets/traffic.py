"""Live traffic widgets: smooth area graph + stat chips, in Dewberry colours.

Recoloured from Mulberry: download rides the blue–cyan accent, upload the
violet accent. The only permitted glow is the soft halo on the newest sample.
"""
from __future__ import annotations

from collections import deque

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ...utils import icons

DOWN_COLOR = QColor("#22D3EE")   # cyan (download)
UP_COLOR = QColor("#8B5CF6")     # violet (upload)
GRID = QColor(255, 255, 255, 11)


class TrafficGraph(QFrame):
    """Smooth area chart of download/upload speed (newest sample on the right)."""

    SAMPLES = 90

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Inset")
        self.setMinimumHeight(150)
        self.down = deque(maxlen=self.SAMPLES)
        self.up = deque(maxlen=self.SAMPLES)

    def add_sample(self, up_bps: float, down_bps: float) -> None:
        self.up.append(max(0.0, up_bps))
        self.down.append(max(0.0, down_bps))
        self.update()

    def clear(self) -> None:
        self.up.clear()
        self.down.clear()
        self.update()

    def _points(self, series, peak, w, h, pad):
        n = len(series)
        step = w / max(1, self.SAMPLES - 1)
        x0 = w - (n - 1) * step
        return [QPointF(x0 + i * step, h - (v / peak) * (h - pad) - 4)
                for i, v in enumerate(series)]

    @staticmethod
    def _smooth(pts):
        path = QPainterPath()
        path.moveTo(pts[0])
        for i in range(1, len(pts)):
            mid = QPointF((pts[i - 1].x() + pts[i].x()) / 2,
                          (pts[i - 1].y() + pts[i].y()) / 2)
            path.quadTo(pts[i - 1], mid)
        path.lineTo(pts[-1])
        return path

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        pad = 18

        clip = QPainterPath()
        clip.addRoundedRect(1, 1, w - 2, h - 2, 12, 12)
        p.setClipPath(clip)

        pen = QPen(GRID, 1)
        pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        for i in (1, 2, 3):
            y = h * i / 4
            p.drawLine(QPointF(0, y), QPointF(w, y))

        if len(self.down) < 2:
            return
        peak = max(max(self.down, default=0), max(self.up, default=0), 1024.0)
        for series, color in ((self.down, DOWN_COLOR), (self.up, UP_COLOR)):
            pts = self._points(series, peak, w, h, pad)
            line = self._smooth(pts)
            fill = QPainterPath(line)
            fill.lineTo(pts[-1].x(), h)
            fill.lineTo(pts[0].x(), h)
            fill.closeSubpath()
            grad = QLinearGradient(0, 0, 0, h)
            top = QColor(color)
            top.setAlpha(58)
            bottom = QColor(color)
            bottom.setAlpha(0)
            grad.setColorAt(0, top)
            grad.setColorAt(1, bottom)
            p.fillPath(fill, grad)
            p.setPen(QPen(color, 2.0, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(line)
            p.setPen(Qt.PenStyle.NoPen)
            halo = QColor(color)
            halo.setAlpha(60)
            p.setBrush(halo)
            p.drawEllipse(pts[-1], 4.5, 4.5)
            p.setBrush(QColor("#F5F7FB"))
            p.drawEllipse(pts[-1], 1.9, 1.9)


class StatChip(QFrame):
    """Tinted icon tile + big speed + small total, for the monitor section."""

    def __init__(self, icon_name: str, color: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Chip")
        self._name = ""
        self._total = "0 B"
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 11, 14, 11)
        row.setSpacing(12)
        c = QColor(color)
        box = QLabel()
        box.setFixedSize(38, 38)
        box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box.setStyleSheet(
            f"background: rgba({c.red()},{c.green()},{c.blue()},0.14);"
            f"border: 1px solid rgba({c.red()},{c.green()},{c.blue()},0.28);"
            "border-radius: 11px;")
        box.setPixmap(icons.pixmap(icon_name, color, 18))
        col = QVBoxLayout()
        col.setSpacing(1)
        self._speed = QLabel("0 B/s")
        self._speed.setStyleSheet(
            "color:#F5F7FB;font-size:17px;font-weight:700;background:transparent;")
        self._sub = QLabel("")
        self._sub.setStyleSheet(
            "color:#7E8AA0;font-size:12px;background:transparent;")
        col.addWidget(self._speed)
        col.addWidget(self._sub)
        row.addWidget(box)
        row.addLayout(col, 1)

    def set_label(self, name: str) -> None:
        self._name = name
        self._refresh()

    def set_values(self, speed_text: str, total_text: str) -> None:
        self._speed.setText(speed_text)
        self._total = total_text
        self._refresh()

    def reset(self) -> None:
        self._speed.setText("0 B/s")
        self._total = "0 B"
        self._refresh()

    def _refresh(self) -> None:
        self._sub.setText(f"{self._name}  \u00b7  {self._total}"
                          if self._name else self._total)
