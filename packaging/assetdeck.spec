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
    "PySide6.QtNetwork",
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

# Módulos Qt pesados não utilizados pelo AssetDeck
qt_excludes = [
    "pytest",
    # QtWebEngine
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    # Qt3D
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    # QML / Quick
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.QtQuick3DRuntimeRender",
    # Multimedia & Audio
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    # Charts & DataVis
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    # PDF
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    # Sensors, Positioning, Location
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtSensors",
    # Hardware & Connectivity
    "PySide6.QtSerialPort",
    "PySide6.QtSerialBus",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    # Web & Networking (non-core)
    "PySide6.QtWebSockets",
    "PySide6.QtWebChannel",
    "PySide6.QtHttpServer",
    # Tooling & Designer
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtUiTools",
    "PySide6.QtTest",
    # Other heavy / unused
    "PySide6.QtSql",
    "PySide6.QtTextToSpeech",
    "PySide6.QtVirtualKeyboard",
]

a = Analysis(
    [os.path.join(SPECPATH, "run_assetdeck.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    noarchive=False,
)

# Filtra binários e dados de módulos Qt excluídos que possam ter sido puxados por hooks
excluded_qt_prefixes = (
    "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6VirtualKeyboard", "Qt6WebEngine",
    "Qt63D", "Qt6Charts", "Qt6Multimedia", "Qt6SpatialAudio", "Qt6Sensors",
    "Qt6Positioning", "Qt6Location", "Qt6Bluetooth", "Qt6Nfc", "Qt6SerialPort",
    "QtQuick", "QtQml", "QtPdf", "QtVirtualKeyboard", "QtWebEngine",
    "Qt3D", "QtCharts", "QtMultimedia", "QtSpatialAudio", "QtSensors",
    "QtPositioning", "QtLocation", "QtBluetooth", "QtNfc", "QtSerialPort",
    "virtualkeyboard", "qpdf",
)
a.binaries = [
    b for b in a.binaries
    if not any(
        prefix.lower() in os.path.basename(b[0]).lower()
        or (len(b) > 1 and isinstance(b[1], str) and prefix.lower() in b[1].lower())
        for prefix in excluded_qt_prefixes
    )
]

excluded_data_prefixes = (
    "PySide6/qml",
    "PySide6/Qt/qml",
    "PySide6/Qt/translations",
)
a.datas = [
    d for d in a.datas
    if not any(d[0].startswith(p) or p in d[0] for p in excluded_data_prefixes)
]

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

# Remove links simbólicos quebrados que hooks do PySide6 possam deixar para trás
internal_dir = os.path.join(DISTPATH, "assetdeck", "_internal")
if os.path.isdir(internal_dir):
    for f in os.listdir(internal_dir):
        fp = os.path.join(internal_dir, f)
        if os.path.islink(fp) and not os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AssetDeck.app",
        bundle_identifier="com.assetdeck.assetdeck",
    )
    import shutil
    shutil.rmtree(os.path.join(DISTPATH, "assetdeck"), ignore_errors=True)
