"""Filesystem locations used by Dewberry."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Folder that contains ``assets/`` (source tree or PyInstaller bundle)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[2]


def assets_dir() -> Path:
    return app_root() / "assets"


def data_dir() -> Path:
    """Per-user writable folder (%APPDATA%/Dewberry on Windows)."""
    if is_windows():
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    p = base / "Dewberry"
    p.mkdir(parents=True, exist_ok=True)
    return p


def core_dir() -> Path:
    """Folder holding xray(.exe), tun2socks(.exe), wintun.dll and geo files.

    A ``core`` folder next to the executable wins (portable mode), otherwise
    the per-user data folder is used.
    """
    portable = (Path(sys.executable).parent if is_frozen() else app_root()) / "core"
    if portable.exists():
        return portable
    p = data_dir() / "core"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def exe_name(base: str) -> str:
    return f"{base}.exe" if is_windows() else base


def xray_path() -> Path:
    return core_dir() / exe_name("xray")


def tun2socks_path() -> Path:
    return core_dir() / exe_name("tun2socks")
