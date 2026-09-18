# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

用法::

    pyinstaller build.spec --noconfirm                          # 目录模式（启动快）
    $env:FMP_ONEFILE="1"; pyinstaller build.spec --noconfirm    # 单文件模式

打包要点
--------
* ``app/ui`` 下的 QML 与 ``app/ui/qmldir``（Theme 单例）必须作为数据一并带上；
* ``FluentUI`` 的 ``qml/`` 目录（QML 控件、fluentuiplugin.dll、图标字体）必须收集，
  否则界面整个加载不出来；
* ``app/sources`` 里的音源是**动态导入**的（``importlib.import_module``），
  PyInstaller 静态分析看不到，必须写进 ``hiddenimports``；
* ``mutagen`` 内部按格式动态派发（mp3/flac/mp4/ogg…），需要全量收集；
* **不要**用 ``collect_submodules("qrcode")``：它会连带拉进 numpy / lxml / scipy
  （``qrcode.image.styledpil`` 用 numpy，``qrcode.image.svg`` 可能用 lxml），
  体积会凭空多出几十 MB。这里只收真正用到的 ``qrcode.image.pil``；
* PySide6 的 hook 会把整个 PySide6 目录下的 Qt DLL 全收进来（其中
  ``Qt6WebEngineCore.dll`` 单个就有 195MB），因此要在 EXE/COLLECT 之前
  对 ``Analysis.binaries`` 做一次过滤。
"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH)  # noqa: F821 - PyInstaller 注入
APP_NAME = "FusionMusicPlayer"
ONEFILE = os.environ.get("FMP_ONEFILE", "0") == "1"
ICON = ROOT / "assets" / "icon.ico"

# ── 数据文件 ────────────────────────────────────────────────
datas = [
    (str(ROOT / "app" / "ui"), "app/ui"),
    (str(ROOT / "assets"), "assets"),
]
datas += collect_data_files("FluentUI", include_py_files=False)
datas += collect_data_files("qrcode", include_py_files=False)

# ── 需要剔除的二进制 ────────────────────────────────────────
DROP_QT_DLLS = {
    "Qt6WebEngineCore.dll",
    "Qt6WebEngineQuick.dll",
    "Qt6WebEngineQuickDelegatesQml.dll",
    "Qt6Pdf.dll",
    "Qt6PdfQuick.dll",
    "Qt6Designer.dll",
    "Qt6DesignerComponents.dll",
    "Qt6Quick3D.dll",
    "Qt6Quick3DAssetImport.dll",
    "Qt6Quick3DAssetUtils.dll",
    "Qt6Quick3DEffects.dll",
    "Qt6Quick3DHelpers.dll",
    "Qt6Quick3DParticles.dll",
    "Qt6Quick3DRuntimeRender.dll",
    "Qt6Quick3DUtils.dll",
    "Qt6Quick3DXr.dll",
    # 注意：Qt6ShaderTools.dll 不能删 —— Qt5Compat.GraphicalEffects 的
    # qtgraphicaleffectsprivateplugin.dll 依赖它（FluentUI 的 FluClip 会用到），
    # 删掉后 QML 会报 "无法加载库 ... 找不到指定的模块"。
    "Qt6Charts.dll",
    "Qt6DataVisualization.dll",
    "Qt6DataVisualizationqml.dll",
    "Qt6Graphs.dll",
    "Qt6Bluetooth.dll",
    "Qt6Nfc.dll",
    "Qt6Sql.dll",
    "Qt6Test.dll",
    "Qt6Sensors.dll",
    "Qt6SensorsQuick.dll",
    "Qt6SerialPort.dll",
    "Qt6RemoteObjects.dll",
    "Qt6RemoteObjectsQml.dll",
    "Qt6Scxml.dll",
    "Qt6ScxmlQml.dll",
    "Qt6StateMachine.dll",
    "Qt6StateMachineQml.dll",
    "Qt6Location.dll",
    "Qt6Positioning.dll",
    "Qt6PositioningQuick.dll",
    "Qt6Help.dll",
    "Qt6TextToSpeech.dll",
    "Qt6SpatialAudio.dll",
    "Qt63DCore.dll",
    "Qt63DRender.dll",
    "Qt63DAnimation.dll",
    "Qt63DInput.dll",
    "Qt63DLogic.dll",
    "Qt63DExtras.dll",
    # 我们强制使用 Basic 风格（见 application.py 的 QQuickStyle.setStyle），
    # 其余 Controls 风格用不到
    "Qt6QuickControls2Imagine.dll",
    "Qt6QuickControls2Material.dll",
    "Qt6QuickControls2Universal.dll",
    "Qt6QuickControls2Fusion.dll",
    "Qt6QuickControls2Windows.dll",
}

# Pillow 只用来给 qrcode 渲染 PNG，其它解码器都可以去掉
DROP_PIL_BINARIES = {"_avif.cp314-win_amd64.pyd"}

DROP_BINARY_NAMES = DROP_QT_DLLS | DROP_PIL_BINARIES
DROP_DATA_PARTS = (
    "qtwebengine_locales",
    "resources/qtwebengine",
    "translations/qtwebengine",
    # 未使用的 QML 控件风格
    "qml/QtQuick/Controls/Imagine",
    "qml/QtQuick/Controls/Material",
    "qml/QtQuick/Controls/Universal",
    "qml/QtQuick/Controls/Fusion",
    "qml/QtQuick/Controls/Windows",
    "qml/QtQuick/Controls/designer",
    # 仅用于 QML 调试
    "plugins/qmltooling",
)


def _filter_toc(toc, drop_names, drop_parts=()):
    """按文件名 / 路径片段过滤 PyInstaller 的 TOC；必须在 EXE/COLLECT 之前调用。"""
    kept = []
    for entry in toc:
        name = str(entry[0]).replace("\\", "/")
        if Path(name).name in drop_names:
            continue
        if any(part in name for part in drop_parts):
            continue
        kept.append(entry)
    return kept


def _filter_translations(toc, keep_locales=("zh_CN",)):
    """Qt 自带翻译只保留中文：界面全部由我们自己绘制，其余语言用不到。"""
    kept = []
    for entry in toc:
        name = str(entry[0]).replace("\\", "/")
        if "/translations/" in name and name.endswith(".qm"):
            if not any(loc in Path(name).stem for loc in keep_locales):
                continue
        kept.append(entry)
    return kept


# ── 隐藏导入 ────────────────────────────────────────────────
hiddenimports = [
    # app/sources/__init__.py 里用 importlib 动态导入的音源
    "app.sources.base",
    "app.sources.utils",
    "app.sources.wy",
    "app.sources.kw",
    "app.sources.kg",
    "app.sources.mg",
    "app.sources.tx",
    "app.sources.bili",
    "app.sources.netease",
    # Qt 模块（QML 运行时用得到，静态分析未必全部可见）
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",
    "PySide6.QtSvg",
    "PySide6.QtWidgets",
    # 只收 qrcode 的 PIL 后端（见文件头注释）
    "qrcode",
    "qrcode.image.base",
    "qrcode.image.pil",
    # 动态加载的第三方
    "mutagen",
    "cryptography",
]
hiddenimports += collect_submodules("mutagen")
hiddenimports += collect_submodules("app")

excludes = [
    # 注意：不要排除 distutils / unittest —— setuptools 的 distutils 与
    # PyInstaller 的 pre-safe-import 钩子会冲突（ValueError: already imported）。
    "tkinter",
    "numpy",
    "scipy",
    "lxml",
    "pandas",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtPdf",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtLocation",
    "PySide6.QtSerialPort",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtTextToSpeech",
    "PySide6.QtSpatialAudio",
]

block_cipher = None

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 过滤必须在 EXE / COLLECT 之前进行
a.binaries = _filter_toc(a.binaries, DROP_BINARY_NAMES)
a.datas = _filter_toc(a.datas, set(), DROP_DATA_PARTS)
a.datas = _filter_translations(a.datas)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

if ONEFILE:
    exe = EXE(  # noqa: F821
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        icon=str(ICON) if ICON.exists() else None,
    )
else:
    exe = EXE(  # noqa: F821
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        icon=str(ICON) if ICON.exists() else None,
    )
    coll = COLLECT(  # noqa: F821
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME,
    )
