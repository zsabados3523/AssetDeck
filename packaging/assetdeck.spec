# -*- mode: python ; coding: utf-8 -*-
"""Especificação do PyInstaller para o AssetDeck (Linux, macOS, Windows)."""

import os
import sys
from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "assetdeck", "ui", "theme.qss"), os.path.join("assetdeck", "ui")),
    (os.path.join(ROOT, "assetdeck", "ui", "icons"), os.path.join("assetdeck", "ui", "icons")),
    (os.path.join(ROOT, "assetdeck", "ui", "fonts"), os.path.join("assetdeck", "ui", "fonts")),
    (os.path.join(ROOT, "assetdeck", "db", "migrations"), os.path.join("assetdeck", "db", "migrations")),
    (os.path.join(ROOT, "assetdeck", "blender", "scripts"), os.path.join("assetdeck", "blender", "scripts")),
    (os.path.join(ROOT, "blender_addon"), "blender_addon"),
]

binaries = []

hiddenimports = [
    "PySide6",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "OpenEXR",
    "Imath",
    "cv2",
    "assimp_py",
    "PIL",
    "PIL.Image",
    "numpy",
]

# Garante a coleta de binários, dados e submódulos das dependências críticas
for pkg in ("OpenEXR", "cv2", "assimp_py", "PIL", "numpy"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas.extend(pkg_datas)
        binaries.extend(pkg_binaries)
        hiddenimports.extend(pkg_hidden)
    except Exception:
        pass

a = Analysis(
    [os.path.join(SPECPATH, "run_assetdeck.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="assetdeck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="assetdeck",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AssetDeck.app",
        bundle_identifier="com.assetdeck.assetdeck",
    )
