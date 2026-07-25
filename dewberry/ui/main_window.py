"""Main window: sidebar navigation + stacked pages + live telemetry + tray.

The window owns both networking subsystems — the Xray/TUN ConnectionManager
and the native Shade SniController — and drives a single 1s telemetry timer
that feeds the dashboard. English-only, frameless, unified design system.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QSizeGrip, QStackedWidget,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from .. import version
from ..utils import icons
from ..utils import sysinfo
from ..utils.paths import assets_dir
from .pages.about import AboutPage
from .pages.configs import ConfigsPage
from .pages.docs import DocsPage
from .pages.home import HomePage
from .pages.monitor import MonitorPage
from .pages.settings import SettingsPage
from .pages.sni import SniPage
from .widgets.titlebar import TitleBar

NAV = [
    ("Dashboard", "grid"),
    ("SNI Management", "shield"),
    ("Configurations", "server"),
    ("Monitor", "activity"),
    ("Settings", "sliders"),
    ("Documentation", "book"),
    ("About", "info"),
]

_ERRORS = {
    "no_server": "No configuration selected. Add one on the Configurations page.",
    "no_core": "The Xray core binary was not found in the core folder.",
    "no_tun2socks": "tun2socks was not found in the core folder.",
    "need_admin": "Administrator rights are required for TUN mode.",
    "core_exit": "The Xray core exited unexpectedly. Check the logs.",
    "sni_start_failed": "The SNI engine failed to start. See the logs for details.",
    "sni_stopped": "The SNI engine stopped unexpectedly.",
}


class MainWindow(QMainWindow):
    def __init__(self, store, conn, sni):
        super().__init__()
        self.store, self.conn, self.sni = store, conn, sni
        self._quitting = False

        self.setWindowTitle(version.APP_NAME)
        self.setMinimumSize(880, 600)
        self.resize(1280, 820)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        icon_path = assets_dir() / "icons" / "logo_256.png"
        self.app_icon = QIcon(str(icon_path))
        self.setWindowIcon(self.app_icon)

        # ---------------- sidebar
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(208)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(8, 18, 8, 14)
        side.setSpacing(4)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(12, 0, 12, 8)
        brand_row.setSpacing(11)
        logo = QLabel()
        pm = QPixmap(str(icon_path))
        if not pm.isNull():
            logo.setPixmap(pm.scaled(30, 30, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))
        name_col = QVBoxLayout()
        name_col.setSpacing(0)
        brand = QLabel(version.APP_NAME)
        brand.setObjectName("BrandName")
        name_col.addWidget(brand)
        brand_row.addWidget(logo)
        brand_row.addLayout(name_col, 1)
        side.addLayout(brand_row)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setIconSize(QSize(19, 19))
        for label, ic in NAV:
            item = QListWidgetItem(icons.icon(ic, icons.MUTED, 19,
                                              selected=icons.ACCENT_SOFT), label)
            self.nav.addItem(item)
        side.addWidget(self.nav, 1)

        footer = QLabel(f"v{version.APP_VERSION}  \u00b7  {version.DEVELOPER_NAME}")
        footer.setObjectName("Faint")
        footer.setContentsMargins(12, 6, 12, 0)
        side.addWidget(footer)

        # ---------------- pages
        self.pages = QStackedWidget()
        self.home = HomePage(conn, sni, store)
        self.sni_page = SniPage(sni, store)
        self.configs = ConfigsPage(conn, store)
        self.monitor = MonitorPage(conn, sni, store)
        self.settings = SettingsPage(store)
        self.docs = DocsPage()
        self.about = AboutPage()
        for page in (self.home, self.sni_page, self.configs, self.monitor,
                     self.settings, self.docs, self.about):
            self.pages.addWidget(page)

        # ---------------- shell
        central = QWidget()
        central.setObjectName("Window")
        central.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.titlebar = TitleBar(self)
        outer.addWidget(self.titlebar)

        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        side_wrap = QVBoxLayout()
        side_wrap.setContentsMargins(16, 8, 0, 20)
        side_wrap.addWidget(sidebar)
        root.addLayout(side_wrap)
        root.addWidget(self.pages, 1)
        outer.addWidget(body, 1)

        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 7, 7)
        grip_row.addStretch()
        grip_row.addWidget(QSizeGrip(central))
        outer.addLayout(grip_row)
        self.setCentralWidget(central)

        self.nav.currentRowChanged.connect(self._on_nav)
        self.nav.setCurrentRow(0)

        self.conn.error.connect(self._show_error)
        self.sni.error.connect(self._show_error)
        self.conn.state_changed.connect(lambda _s: self._update_tray())
        self.sni.state_changed.connect(lambda _s: self._update_tray())

        self._build_tray()
        self._start_telemetry()

    # ---------------- navigation
    def _on_nav(self, row: int) -> None:
        self.pages.setCurrentIndex(row)
        if self.pages.currentWidget() is self.configs:
            self.configs.refresh()

    # ---------------- telemetry
    def _start_telemetry(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(int(self.store.get("stats_interval_ms", 1000)))
        self._timer.timeout.connect(self.home.tick)
        self._timer.timeout.connect(self.monitor.tick)
        self._timer.start()

        # slow background refresh for network + resource info
        self._slow = QTimer(self)
        self._slow.setInterval(5000)
        self._slow.timeout.connect(self._refresh_resources)
        self._slow.start()
        self._refresh_network_async()
        self._refresh_resources()

    def _refresh_resources(self) -> None:
        self.monitor.set_resources(sysinfo.cpu_percent(), sysinfo.memory_percent())
        # refresh public IP only while a tunnel is up (and on first call)
        if self.conn.state == "connected" or self.home._pub_ip == "\u2014":
            self._refresh_network_async()

    def _refresh_network_async(self) -> None:
        def worker():
            local = sysinfo.local_ip()
            dns = sysinfo.dns_servers()
            iface = sysinfo.active_interface()
            pub, country = sysinfo.public_ip()
            self.home.set_network_info(pub, country, local, dns, iface)
            self.monitor.set_network_info(pub, country, local, dns, iface)
        threading.Thread(target=worker, daemon=True).start()

    # ---------------- tray
    def _build_tray(self) -> None:
        icon_path = assets_dir() / "icons" / "logo_256.png"
        self.tray_icon_on = QIcon(str(icon_path))
        gray = QImage(str(icon_path)).convertToFormat(QImage.Format.Format_Grayscale8)
        self.tray_icon_off = (QIcon(QPixmap.fromImage(gray))
                              if not gray.isNull() else self.app_icon)
        self.tray = QSystemTrayIcon(self.tray_icon_off, self)
        menu = QMenu()
        self.act_show = QAction("Show Dewberry", self)
        self.act_vpn = QAction("Connect VPN", self)
        self.act_sni = QAction("Enable SNI engine", self)
        self.act_quit = QAction("Quit", self)
        self.act_show.triggered.connect(self._show_from_tray)
        self.act_vpn.triggered.connect(self.conn.toggle)
        self.act_sni.triggered.connect(self.sni.toggle)
        self.act_quit.triggered.connect(self.quit_app)
        menu.addAction(self.act_show)
        menu.addAction(self.act_vpn)
        menu.addAction(self.act_sni)
        menu.addSeparator()
        menu.addAction(self.act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._show_from_tray()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._update_tray()

    def _show_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _update_tray(self) -> None:
        vpn_on = self.conn.state == "connected"
        sni_on = self.sni.state == "connected"
        self.tray.setIcon(self.tray_icon_on if (vpn_on or sni_on)
                          else self.tray_icon_off)
        self.act_vpn.setText("Disconnect VPN" if vpn_on else "Connect VPN")
        self.act_sni.setText("Disable SNI engine" if sni_on else "Enable SNI engine")
        state = "Protected" if (vpn_on and sni_on) else (
            "Active" if (vpn_on or sni_on) else "Idle")
        self.tray.setToolTip(f"{version.APP_NAME} \u2014 {state}")

    # ---------------- errors / lifecycle
    def _show_error(self, code: str) -> None:
        QMessageBox.warning(self, version.APP_NAME,
                            _ERRORS.get(code, code))

    def closeEvent(self, event):  # noqa: N802
        if self._quitting or not self.store.get("close_to_tray", True):
            self._teardown()
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(version.APP_NAME, "Still running in the tray.",
                              self.tray_icon_off, 2500)

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.instance().quit()

    def _teardown(self) -> None:
        try:
            self.conn.shutdown()
        except Exception:
            pass
        try:
            self.sni.shutdown()
        except Exception:
            pass
