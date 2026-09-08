# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec.

Build with:
    pip install -r requirements-dev.txt
    pyinstaller csv-viewer.spec

Produces dist/CSVViewer/CSVViewer.exe (one-folder build: starts fast because
nothing has to be unpacked at launch, unlike a --onefile build).
"""
from PyInstaller.utils.hooks import collect_data_files

# tkinterdnd2 ships a Tcl/Tk extension (the tkdnd folder) that PyInstaller
# does not pick up on its own -- without this, drag-and-drop breaks in the build.
datas = collect_data_files("tkinterdnd2")
datas += [("assets/icon.ico", "assets")]

a = Analysis(
    ["viewer.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
