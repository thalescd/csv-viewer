# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec.

Build with:
    pip install -r requirements-dev.txt
    pyinstaller csv-viewer.spec

Produces dist/CSVViewer/CSVViewer.exe (one-folder build: starts fast because
nothing has to be unpacked at launch, unlike a --onefile build).
"""
import os
import sys

from PyInstaller.utils.hooks import collect_data_files

# tkinterdnd2 ships a Tcl/Tk extension (the tkdnd folder) that PyInstaller
# does not pick up on its own -- without this, drag-and-drop breaks in the build.
# It ships a copy per OS/architecture, and tkinterdnd2 picks one at runtime, so
# every folder for a different OS is dead weight (~1.2 MB on a Windows build).
TKDND_OS = {"win32": "win", "darwin": "osx"}.get(sys.platform, "linux")

datas = [
    (src, dest) for src, dest in collect_data_files("tkinterdnd2")
    if "tkdnd" not in dest or os.path.basename(dest).startswith(TKDND_OS)
]
# the .ico is the Windows window/exe icon; the .png is what Tk can use for
# the window icon on Linux (see _set_window_icon)
datas += [("assets/icon.ico", "assets"), ("assets/icon.png", "assets")]

a = Analysis(
    ["viewer.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # OpenSSL (~4 MB) used to be excluded here; the update check needs HTTPS now
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CSVViewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI app: no console window behind it
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CSVViewer",
)
