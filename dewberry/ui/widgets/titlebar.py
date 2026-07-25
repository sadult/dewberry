"""Frameless-window title bar with macOS-style traffic-light buttons.

Matches the Mulberry family look: a brand mark on the left and three round
close / minimize / zoom controls on the right that reveal their glyphs on
hover, drawn entirely with QPainter (no native chrome).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ...utils import icons
from ...version import APP_NAME


class TrafficLight(QPushButton):
    """A single macOS-style circular button with a hover glyph."""

    DIAMETER = 13

    def __init__(self, color: str, glyph: str, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._glyph = glyph  # "close" | "min" | "zoom"
        self._hover = False
        self.setFixedSize(self.DIAMETER + 6, self.DIAMETER + 6)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet("background: transparent; border: none;")

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = self.DIAMETER
        x = (self.width() - d) / 2
        y = (self.height() - d) / 2

        active = self._hover or self.window().isActiveWindow()
        rim = QColor(0, 0, 0, 60)
        p.setPen(QPen(rim, 1))
        p.setBrush(self._color if active else QColor(60, 68, 92))
        p.drawEllipse(QPointF(x + d / 2, y + d / 2), d / 2, d / 2)

        if not self._hover:
            return
        ink = QColor(0, 0, 0, 150)
        pen = QPen(ink, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        cx, cy, r = x + d / 2, y + d / 2, d / 4.4
        if self._glyph == "close":
            p.drawLine(QPointF(cx - r, cy - r), QPointF(cx + r, cy + r))
            p.drawLine(QPointF(cx - r, cy + r), QPointF(cx + r, cy - r))
        elif self._glyph == "min":
            p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
        else:  # zoom
            p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
            p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))


class TitleBar(QWidget):
    """Draggable top strip: brand on the left, traffic lights on the right."""

    HEIGHT = 44

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(self.HEIGHT)
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 16, 0)
        row.setSpacing(9)

        dot = QLabel()
        dot.setPixmap(icons.pixmap("shield", icons.ACCENT_SOFT, 15))
        title = QLabel(APP_NAME)
        title.setObjectName("TitleTitle")
        row.addWidget(dot)
        row.addWidget(title)
        row.addStretch()

        self.btn_close = TrafficLight("#FF5F57", "close")
        self.btn_min = TrafficLight("#FEBC2E", "min")
        self.btn_zoom = TrafficLight("#28C840", "zoom")
        self.btn_close.clicked.connect(window.close)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_zoom.clicked.connect(self._toggle_zoom)
        row.addWidget(self.btn_min)
        row.addWidget(self.btn_zoom)
        row.addWidget(self.btn_close)

    def _toggle_zoom(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_zoom()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
