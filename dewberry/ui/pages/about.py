"""About — hero, description, version/status, credits, license, privacy."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from ... import version
from ...utils import icons
from ...utils.paths import assets_dir
from ..widgets.common import Card, CardHeader, StatField, muted

CREDITS = [
    ("Xray-core", "github.com/XTLS/Xray-core"),
    ("tun2socks", "github.com/xjasonlyu/tun2socks"),
    ("Wintun", "wintun.net"),
    ("WinDivert", "reqrypt.org/windivert.html"),
    ("Iran-v2ray-rules", "github.com/chocolate4u/Iran-v2ray-rules"),
    ("Inter font", "rsms.me/inter"),
    ("PySide6 / Qt", "qt.io"),
]

THIRD_PARTY = [
    ("Xray-core", "MPL-2.0"),
    ("tun2socks", "GPL-3.0"),
    ("Wintun", "Prebuilt Binaries License"),
    ("WinDivert", "LGPL-3.0 / GPL-3.0"),
    ("Iran-v2ray-rules", "GPL-3.0"),
    ("Inter", "OFL-1.1"),
    ("PySide6 / Qt", "LGPL-3.0"),
]

# Six actions, laid out 3 x 2.
LINKS = (
    ("refresh", "Check for updates", f"{version.PROJECT_URL}/releases", True),
    ("globe", "Website", version.WEBSITE_URL, False),
    ("github", "GitHub", version.PROJECT_URL, False),
    ("alert", "Report a bug", f"{version.PROJECT_URL}/issues", False),
    ("send", "Telegram", version.TELEGRAM_URL, False),
    ("mail", "Email", f"mailto:{version.DEVELOPER_EMAIL}", False),
)

_PRIVACY = (
    "Dewberry runs entirely on your device. It does not collect, transmit or "
    "sell personal data, and it has no analytics or telemetry. Your "
    "configurations, SNI settings and logs are stored locally in your "
    "per-user Dewberry folder and never leave your machine except as network "
    "traffic you explicitly route through your own servers."
)


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        host = QWidget()
        host.setObjectName("Page")
        root = QVBoxLayout(host)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(host)

        root.addWidget(self._hero())
        root.addWidget(self._description())
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self._info(), 1)
        row.addWidget(self._credits(), 1)
        root.addLayout(row)
        root.addWidget(self._licenses())
        root.addWidget(self._privacy())
        root.addStretch()

    # ------------------------------------------------------------ hero
    def _hero(self) -> Card:
        hero = Card()
        hv = QVBoxLayout(hero)
        hv.setContentsMargins(24, 28, 24, 24)
        hv.setSpacing(6)
        hv.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        logo = QLabel()
        pix = QPixmap(str(assets_dir() / "icons" / "logo_256.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hv.addWidget(logo)

        brand = QLabel(version.APP_NAME)
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet("font-size:26px;font-weight:800;background:transparent;")
        hv.addWidget(brand)

        tag = QLabel(version.TAGLINE)
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tag.setObjectName("Muted")
        hv.addWidget(tag)

        descriptor = QLabel("SNI spoofing \u00b7 Xray/V2Ray \u00b7 TUN \u2014 unified")
        descriptor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        descriptor.setStyleSheet(
            "color:#60A5FA;font-size:12px;font-weight:600;background:transparent;")
        hv.addWidget(descriptor)
        hv.addSpacing(6)

        pill = QLabel(f"v{version.APP_VERSION}  \u00b7  engine v{version.ENGINE_VERSION}")
        pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pill.setStyleSheet(
            "background:rgba(59,130,246,0.10);border:1px solid rgba(59,130,246,0.30);"
            "border-radius:11px;padding:4px 14px;color:#8FB4FF;"
            "font-size:11px;font-weight:700;")
        prow = QHBoxLayout()
        prow.addStretch()
        prow.addWidget(pill)
        prow.addStretch()
        hv.addLayout(prow)
        hv.addSpacing(10)

        actions = QGridLayout()
        actions.setHorizontalSpacing(8)
        actions.setVerticalSpacing(8)
        for i, (icon_name, label, url, primary) in enumerate(LINKS):
            btn = QPushButton(f"  {label}")
            btn.setObjectName("Primary" if primary else "Ghost")
            btn.setIcon(icons.icon(icon_name, "#FFFFFF" if primary else icons.MUTED, 16))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            actions.addWidget(btn, i // 3, i % 3)
        hv.addLayout(actions)
        return hero

    def _description(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(10)
        lay.addWidget(CardHeader("info", "About Dewberry", icons.ACCENT))
        text = QLabel(
            "Dewberry is a premium desktop client that unifies SNI spoofing "
            "and Xray/V2Ray connectivity into one cohesive experience. It pairs "
            "the native Shade engine — a fake TLS/SNI tunnel — with a fully "
            "working TUN implementation, configuration management and routing "
            "inherited from the Mulberry ecosystem, so you can spoof, connect "
            "and route all system traffic without any external tools.")
        text.setWordWrap(True)
        text.setStyleSheet("color:#C6CEDE;background:transparent;font-size:13px;")
        lay.addWidget(text)
        return card

    def _info(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(CardHeader("cpu", "Version & build", icons.ACCENT_HOT))
        lay.addWidget(StatField("Application", f"v{version.APP_VERSION}"))
        lay.addWidget(StatField("Shade engine", f"v{version.ENGINE_VERSION}"))
        lay.addWidget(StatField("Build", version.APP_BUILD))
        lay.addWidget(StatField("Developer", version.DEVELOPER_NAME))
        lay.addWidget(StatField("License", version.LICENSE_NAME))
        return card

    def _credits(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(CardHeader("heart", "Credits", icons.ACCENT_CYAN))
        for name, url in CREDITS:
            lay.addWidget(StatField(name, url))
        return card

    def _licenses(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(CardHeader("file-text", "Licenses", icons.ACCENT_SOFT))
        lay.addWidget(muted(
            f"{version.APP_NAME} is released under the {version.LICENSE_NAME}. "
            f"{version.COPYRIGHT}. Free for noncommercial use."))
        for name, lic in THIRD_PARTY:
            lay.addWidget(StatField(name, lic))
        return card

    def _privacy(self) -> Card:
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(10)
        lay.addWidget(CardHeader("lock", "Privacy", icons.GOOD))
        text = QLabel(_PRIVACY)
        text.setWordWrap(True)
        text.setStyleSheet("color:#C6CEDE;background:transparent;font-size:13px;")
        lay.addWidget(text)
        return card
