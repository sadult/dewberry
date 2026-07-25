"""Dewberry — entry point.

Run from source:  python main.py
Build for Windows: scripts/build_windows.bat  (see build/dewberry.spec)

Dewberry unifies the native Shade SNI-spoofing engine with Xray/V2Ray + TUN
connectivity in a single desktop product — the flagship of the Mulberry family.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from dewberry import version
from dewberry.core.connection import ConnectionManager
from dewberry.core.sni_controller import SniController
from dewberry.storage.store import Store
from dewberry.ui.main_window import MainWindow
from dewberry.utils.fonts import app_font, load_fonts
from dewberry.utils.paths import assets_dir


def main() -> int:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "MersadShahidi.Dewberry")
        except Exception:
            pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(version.APP_NAME)
    app.setOrganizationName(version.DEVELOPER_NAME)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(assets_dir() / "icons" / "logo_256.png")))

    store = Store()
    conn = ConnectionManager(store)
    sni = SniController(store)

    load_fonts()
    app.setFont(app_font("en"))

    qss = assets_dir() / "theme" / "dewberry.qss"
    if qss.exists():
        style = qss.read_text(encoding="utf-8")
        style = style.replace("ASSETS", assets_dir().as_posix())
        app.setStyleSheet(style)

    window = MainWindow(store, conn, sni)
    if store.get("start_minimized", False):
        window.hide()
    else:
        window.show()

    # optional auto-start behaviours
    if store.get("auto_connect", False) and store.active_server():
        conn.connect_server()
    if store.get("auto_start_sni", False):
        sni.connect()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
