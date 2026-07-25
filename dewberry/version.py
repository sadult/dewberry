"""Application identity & constants for Dewberry.

Dewberry is the sister application of Mulberry: it unifies SNI spoofing
(the Shade Engine subsystem) and Xray/V2Ray tunnelling with a fully working
Windows TUN implementation into a single, cohesive product.
"""

APP_NAME = "Dewberry"
APP_VERSION = "1.0.0"
APP_BUILD = "2026.07"
APP_ID = "app.dewberry.client"

# The embedded SNI spoofing subsystem carries its own engine version so it can
# evolve independently of the shell around it (surfaced on the dashboard).
ENGINE_NAME = "Shade"
ENGINE_VERSION = "1.0.0"

TAGLINE = "Unified secure tunneling."
TAGLINE_LONG = "SNI spoofing and Xray tunnelling, in one engine."

DEVELOPER_NAME = "Mersad Shahidi"
DEVELOPER_EMAIL = "mercvd@icloud.com"
PROJECT_URL = "https://github.com/sadult/dewberry"
WEBSITE_URL = "https://mercads.ir/hub"
TELEGRAM_URL = "https://t.me/bitologist"
LICENSE_NAME = "PolyForm Noncommercial 1.0.0"
COPYRIGHT = "Copyright (c) 2026 Mersad Shahidi"

# Default source for the Configurations "Fetch" action. Points at a raw text
# document holding one share-link per line (vless://, vmess://, ...).
DEFAULT_FETCH_URL = (
    "https://raw.githubusercontent.com/sadult/dewberry/main/configs.md"
)

USER_AGENT = f"Dewberry/{APP_VERSION}"
URL_TEST_DEFAULT = "http://www.gstatic.com/generate_204"
