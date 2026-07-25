"""Xray/V2Ray configuration management for Dewberry.

Two acquisition paths, no subscriptions:
  * fetch_from_github(url)  — download a raw text/markdown document from a
    GitHub repository and parse every share-link it contains.
  * import_configs_md()     — read a ``configs.md`` file sitting next to the
    running executable and parse it the same way.

Both funnel through :func:`extract_links`, which is markdown-aware (it strips
code fences and inline formatting before delegating to the battle-tested
``links.parse_links`` reused from Mulberry).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import requests

from ..version import USER_AGENT
from .links import parse_links


def _exe_dir() -> Path:
    """Directory that holds the running executable (or the project root)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def configs_md_path() -> Path:
    return _exe_dir() / "configs.md"


def _to_raw_github(url: str) -> str:
    """Best-effort rewrite of a GitHub *blob* URL into its raw form."""
    url = url.strip()
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com")
        url = url.replace("/blob/", "/")
    return url


def extract_links(text: str) -> list[dict]:
    """Parse every supported share-link out of a markdown/plain document."""
    # drop fenced code blocks' backticks but keep their content
    text = text.replace("```", "\n")
    # strip common inline markdown wrappers around links
    text = re.sub(r"[`*>]", " ", text)
    return parse_links(text)


def fetch_from_github(url: str, timeout: int = 20) -> list[dict]:
    """Download and parse configurations from a GitHub repository/raw URL."""
    resp = requests.get(
        _to_raw_github(url),
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    resp.raise_for_status()
    return extract_links(resp.text)


def import_configs_md(path: Path | None = None) -> list[dict]:
    """Read and parse the local ``configs.md`` next to the executable."""
    path = path or configs_md_path()
    if not path.exists():
        raise FileNotFoundError(str(path))
    return extract_links(path.read_text(encoding="utf-8", errors="replace"))
