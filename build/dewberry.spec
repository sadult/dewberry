# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Dewberry (Windows, one-folder build).

Build:  pyinstaller build/dewberry.spec
Output: dist/Dewberry/Dewberry.exe

Drop xray.exe, tun2socks.exe, wintun.dll, geoip.dat and geosite.dat into a
``core`` folder beside the produced Dewberry.exe (portable core), or into the
per-user %APPDATA%/Dewberry/core folder.
"""
import os

block_cipher = None
ROOT = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
]

hiddenimports = [
    "pydivert",
    "PySide6.QtSvg",
]

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Dewberry",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join(ROOT, "assets", "icons", "dewberry.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Dewberry",
)
