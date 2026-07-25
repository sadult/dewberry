"""Font loading: Vazirmatn for Persian, Inter for English."""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

from .paths import assets_dir

FA_FAMILY = "Vazirmatn"
EN_CANDIDATES = ("Inter", "Inter Variable", "InterVariable",
                 "Space Grotesk", "Segoe UI")


def load_fonts() -> list[str]:
    """Register all bundled TTFs. Returns the list of loaded family names."""
    loaded: list[str] = []
    fonts = assets_dir() / "fonts"
    if fonts.exists():
        for path in sorted(fonts.glob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(path))
            if font_id >= 0:
                loaded += QFontDatabase.applicationFontFamilies(font_id)
    return loaded


def en_family() -> str:
    families = set(QFontDatabase.families())
    for name in EN_CANDIDATES:
        if name in families:
            return name
    return "Segoe UI"


def app_font(lang: str) -> QFont:
    families = set(QFontDatabase.families())
    if lang == "fa" and FA_FAMILY in families:
        family = FA_FAMILY
    else:
        family = en_family()
    font = QFont(family, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font
