"""Tinted SVG line icons (feather style) loaded from assets/icons/ui."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .paths import assets_dir

# palette shortcuts (Dewberry design system)
MUTED = "#7E8AA0"
TEXT = "#E6EAF2"
TEXT_STRONG = "#F5F7FB"
ACCENT = "#3B82F6"        # blue — primary
ACCENT_SOFT = "#60A5FA"
ACCENT_CYAN = "#22D3EE"   # cyan — network / live
ACCENT_HOT = "#8B5CF6"    # violet — secondary
GOOD = "#34D399"
WARN = "#FBBF24"
BAD = "#F87171"


@lru_cache(maxsize=512)
def pixmap(name: str, color: str = MUTED, size: int = 20) -> QPixmap:
    """Render an SVG line icon tinted with `color` at 2x for crispness."""
    path = assets_dir() / "icons" / "ui" / f"{name}.svg"
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(str(path))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * scale, size * scale))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pm.rect(), QColor(color))
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, color: str = MUTED, size: int = 20,
         selected: str | None = None, disabled: str | None = None) -> QIcon:
    """Build a QIcon with optional Selected/Disabled tints."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    if selected:
        ic.addPixmap(pixmap(name, selected, size), QIcon.Mode.Selected)
    if disabled:
        ic.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return ic
