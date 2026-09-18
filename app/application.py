"""应用装配：QGuiApplication + QML 引擎 + 控制器注册。"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from typing import Optional

from PySide6.QtCore import QObject, QUrl, QTimer, Slot
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine

import FluentUI

from . import paths
from .bridges.app import AppController
from .bridges.discover import DiscoverController
from .bridges.library import LibraryController
from .bridges.search import SearchController
from .bridges.settings import SettingsController
from .config import Config
from .core.account import AccountManager
from .core.player import PlayerEngine
from .core.store import Library

logger = logging.getLogger("fusion")

def setup_logging(level: str = "INFO") -> None:
    paths.ensure_dirs()
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-22s %(message)s", datefmt="%H:%M:%S"
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            paths.log_dir() / "fusion.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception as e:  # 日志不可写不应阻塞启动
        print(f"日志文件初始化失败: {e}", file=sys.stderr)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

class Application(QObject):
    """持有全部长生命周期对象，保证不被 GC。"""

    def __init__(self, argv, data_dir: Optional[str] = None):
        super().__init__()
        if data_dir:
            paths.set_data_dir(data_dir)
        paths.ensure_dirs()

        self.config = Config()
        setup_logging(self.config.get("advanced.log_level", "INFO"))

        # FluentUI 基于 Qt Quick Controls 模板，必须使用 Basic 风格，
        # 否则 contentItem/background 的自定义会被原生风格拒绝。
        try:
            from PySide6.QtQuickControls2 import QQuickStyle

            QQuickStyle.setStyle("Basic")
        except Exception as e:  # pragma: no cover
            print(f"设置 Qt Quick Controls 风格失败: {e}", file=sys.stderr)

        self.qt_app = QGuiApplication(argv)
        self.qt_app.setApplicationName(paths.APP_DISPLAY_NAME)
        self.qt_app.setApplicationDisplayName(paths.APP_DISPLAY_NAME)
        self.qt_app.setOrganizationName(paths.ORG_NAME)
        self.qt_app.setApplicationVersion(paths.APP_VERSION)
        self.qt_app.setQuitOnLastWindowClosed(True)

        icon_path = paths.program_dir() / "assets" / "icon.ico"
        if icon_path.exists():
            self.qt_app.setWindowIcon(QIcon(str(icon_path)))

        # ── 业务对象 ────────────────────────────────────────
        self.library = Library()
        self.library.load()

        self.player = PlayerEngine(self.config, self.library)
        self.account = AccountManager(self.config)
        self.search = SearchController(self.config)
        self.library_bridge = LibraryController(self.config, self.library)
        self.discover = DiscoverController(self.config)
        self.settings = SettingsController(self.config)
        self.app = AppController(self.config)

        self._wire()

        # ── QML ─────────────────────────────────────────────
        self.engine = QQmlApplicationEngine()
        FluentUI.init(self.engine)
        # 让 ui/ 目录下的 qmldir（Theme 单例）可被解析
        self.engine.addImportPath(str(paths.qml_dir()))
        ctx = self.engine.rootContext()
        ctx.setContextProperty("player", self.player)
        ctx.setContextProperty("account", self.account)
        ctx.setContextProperty("search", self.search)
        ctx.setContextProperty("library", self.library_bridge)
        ctx.setContextProperty("discover", self.discover)
        ctx.setContextProperty("settings", self.settings)
        ctx.setContextProperty("app", self.app)

        self.engine.warnings.connect(self._on_qml_warning)

    # ── 事件接线 ────────────────────────────────────────────

    def _wire(self) -> None:
        self.app.notify.connect(self._on_notify)
        self.settings.changed.connect(self._on_settings_changed)
        self.player.errorOccurred.connect(self.app.error)
        self.player.statusMessage.connect(self.app.info)
        self.player.fallbackUsed.connect(self._on_fallback)
        self.account.errorOccurred.connect(self.app.error)
        self.account.message.connect(self.app.info)
        self.account.playlistsChanged.connect(self._on_remote_playlists)
        self.search.errorOccurred.connect(self.app.warn)
        self.library_bridge.message.connect(self.app.info)
        self.library_bridge.errorOccurred.connect(self.app.error)
        # 从列表行收藏时，播放栏的爱心状态也要跟着刷新
        self.library_bridge.favoritesChanged.connect(self.player.favoriteStateChanged)
        self.discover.errorOccurred.connect(self.app.warn)
        self.settings.message.connect(self.app.info)
        self.settings.errorOccurred.connect(self.app.error)

    @Slot(str, str)
    def _on_notify(self, level: str, message: str) -> None:
        logger.log(
            {"error": logging.ERROR, "warning": logging.WARNING}.get(level, logging.INFO),
            "%s",
            message,
        )

    @Slot()
    def _on_settings_changed(self) -> None:
        self._apply_source_prefs()

    @Slot(str)
    def _on_fallback(self, source_id: str) -> None:
        from .sources import SOURCE_NAMES

        self.app.warn(f"当前音源不可用，已自动切换到 {SOURCE_NAMES.get(source_id, source_id)}")

    @Slot()
    def _on_remote_playlists(self) -> None:
        self.discover.setRemotePlaylists(self.account.remotePlaylists)

    @Slot(object)
    def _on_qml_warning(self, warnings) -> None:
        for w in warnings:
            logger.warning("QML: %s", w.toString())

    def _apply_source_prefs(self) -> None:
        """把「原唱优先 / 百科兜底」开关同步给网易云音源。"""
        try:
            from .sources import wy_source

            src = wy_source()
            if src is not None:
                src.set_baike_enabled(bool(self.config.get("sources.prefer_original", True)))
        except Exception as e:
            logger.debug("同步原唱开关失败: %s", e)

    # ── 启动 ────────────────────────────────────────────────

    def run(self) -> int:
        main_qml = paths.qml_dir() / "Main.qml"
        if not main_qml.exists():
            logger.error("找不到界面文件: %s", main_qml)
            return 2

        self.engine.load(QUrl.fromLocalFile(str(main_qml)))
        if not self.engine.rootObjects():
            logger.error("QML 加载失败，请查看上方告警")
            return 3

        self._apply_source_prefs()
        self.account.restore()

        if bool(self.config.get("local.scan_on_start", False)) and self.config.get(
            "local.folders", []
        ):
            QTimer.singleShot(1500, self.library_bridge.scan)

        QTimer.singleShot(600, lambda: self.discover.load())

        self.qt_app.aboutToQuit.connect(self.shutdown)
        return self.qt_app.exec()

    def shutdown(self) -> None:
        logger.info("正在退出，保存数据…")
        try:
            self.player.shutdown()
        except Exception as e:
            logger.debug("关闭播放器失败: %s", e)
        try:
            self.library.save()
        except Exception as e:
            logger.warning("保存音乐库失败: %s", e)
        try:
            self.config.save()
        except Exception as e:
            logger.warning("保存配置失败: %s", e)

def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    data_dir = None
    if "--data-dir" in argv:
        i = argv.index("--data-dir")
        if i + 1 < len(argv):
            data_dir = argv[i + 1]
            del argv[i : i + 2]
    app = Application(argv, data_dir=data_dir)
    return app.run()
