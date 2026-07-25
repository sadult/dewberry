"""Documentation — Quick Start, guides, tutorials, troubleshooting, FAQ.

Every section uses an identical structure: a card, a standard header
(icon tile + title) and a single rich-text body. The body is indented to line
up under the title — never under the icon — and no section uses HTML list
indentation, so every block aligns to exactly the same left edge.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ...utils import icons
from ..widgets.common import Card, CardHeader

# Body text is authored as uniform paragraphs. No <ol>/<ul> — numbering and
# bullets are inline so nothing indents differently between sections.
_P = "margin:0 0 10px 0;"
_LEAD = "color:#8FB4FF;font-weight:700;"


def _p(lead: str, body: str) -> str:
    return f"<p style='{_P}'><span style='{_LEAD}'>{lead}</span> {body}</p>"


_QUICK_START = (
    _p("1 \u00b7 Add a configuration.",
       "Open <b>Configurations</b> and use <b>Fetch</b> (a GitHub URL), "
       "<b>Manual Import</b> (a configs.md file beside the app), or <b>Add</b> "
       "to paste a share-link.")
    + _p("2 \u00b7 Pick the fastest server.",
         "Press <b>Ping</b>, select a row, then press <b>Set active</b> "
         "(or double-click it).")
    + _p("3 \u00b7 Tune the SNI engine (optional).",
         "Open <b>SNI Management</b> to adjust the listen address, fake SNI "
         "and destination. The defaults work as-is.")
    + _p("4 \u00b7 Connect.",
         "On the <b>Dashboard</b>, choose your config in the VPN card, then "
         "enable the SNI engine and/or connect the VPN.")
)

_USER_DOCS = (
    _p("SNI spoofing engine.",
       "Dewberry embeds the Shade engine as a native subsystem — no companion "
       "executable. It opens a local listener that forwards traffic to a "
       "destination IP while presenting a forged TLS ClientHello with a chosen "
       "fake SNI, helping traffic blend in on restrictive networks.")
    + _p("Xray / V2Ray + TUN.",
         "The VPN card starts the bundled Xray core and, in TUN mode, routes "
         "the whole system through it using the stable adapter inherited from "
         "Mulberry. Proxy mode instead configures the system SOCKS/HTTP proxy.")
    + _p("Combined use.",
         "Enable the SNI engine and point an Xray config at its listener to "
         "chain both technologies in one flow.")
)

_TUTORIALS = (
    _p("Route everything through TUN.",
       "Settings \u2192 Connection \u2192 set the routing mode to tun, then "
       "connect. Administrator rights are required for the TUN adapter.")
    + _p("Keep Iran / LAN direct.",
         "Enable Bypass Iran routes and Bypass LAN so local and domestic "
         "traffic skips the tunnel.")
    + _p("Export your SNI profile.",
         "SNI Management \u2192 Export to save a JSON you can re-import on "
         "another machine.")
)

_TROUBLESHOOTING = (
    _p("\u201cNeeds administrator\u201d / TUN won\u2019t start.",
       "Run Dewberry as Administrator. The TUN adapter and the SNI engine\u2019s "
       "packet driver both require elevation.")
    + _p("SNI engine fails to start.",
         "Confirm the WinDivert driver is allowed, the listen port is free, and "
         "the destination IP is reachable.")
    + _p("No servers after Fetch.",
         "Verify the URL returns raw text with share-links; try Manual Import "
         "with a local configs.md.")
    + _p("Connected but no traffic.",
         "Re-Ping and switch to a faster server, or toggle the routing mode "
         "between TUN and proxy.")
)

_FAQ = (
    _p("Does Dewberry need Shade Engine installed separately?",
       "No. The engine runs natively inside Dewberry.")
    + _p("Are subscriptions supported?",
         "No — by design. Use Fetch, Manual Import or Add instead.")
    + _p("Is Windows required?",
         "The TUN adapter and SNI packet injection are Windows-only. The "
         "interface and configuration management run anywhere.")
    + _p("Where is my data stored?",
         "Locally, in your per-user Dewberry folder. Nothing is uploaded.")
    + _p("Can I run SNI and VPN at the same time?",
         "Yes — they are independent subsystems and can be enabled together.")
)

_SECTIONS = [
    ("zap", "Quick Start", icons.ACCENT_CYAN, _QUICK_START),
    ("book", "User documentation", icons.ACCENT, _USER_DOCS),
    ("compass", "Tutorials", icons.ACCENT_HOT, _TUTORIALS),
    ("alert", "Troubleshooting", icons.WARN, _TROUBLESHOOTING),
    ("help", "FAQ", icons.ACCENT_SOFT, _FAQ),
]

# Icon tile (34) + header spacing (11) — body lines up under the title.
_BODY_INDENT = 45


class DocsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)

        body = QWidget()
        body.setObjectName("Page")
        root = QVBoxLayout(body)
        root.setContentsMargins(26, 22, 26, 22)
        root.setSpacing(14)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)

        title = QLabel("Documentation")
        title.setObjectName("H1")
        root.addWidget(title)

        for icon_name, heading, tint, html in _SECTIONS:
            root.addWidget(self._section(icon_name, heading, tint, html))
        root.addStretch()

    def _section(self, icon_name, heading, tint, html) -> Card:
        """Identical layout for every documentation section."""
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(CardHeader(icon_name, heading, tint))

        text = QLabel(html)
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        text.setOpenExternalLinks(True)
        text.setContentsMargins(_BODY_INDENT, 0, 4, 0)
        text.setStyleSheet(
            "color:#C6CEDE;background:transparent;font-size:13px;")
        lay.addWidget(text)
        return card
