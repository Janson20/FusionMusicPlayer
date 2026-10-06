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

from . import paths, startup
from .bridges.album import AlbumController
from .bridges.app import AppController
from .bridges.artist import ArtistController
from .bridges.discover import DiscoverController
from .bridges.library import LibraryController
from .bridges.roam import RoamController
from .bridges.search import SearchController
from .bridges.settings import SettingsController
from .bridges.update import UpdateController
from .bridges.wiki import SongWikiController
from .config import Config
from .core.account import AccountManager
from .core.loudness_service import LoudnessService
from .core.player import PlayerEngine
from .core.store import Library
from .lazy import prewarm

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

    def __init__(self, argv, data_dir: Optional[str] = None, splash=None):
        super().__init__()
        self.splash = splash
        if data_dir:
            paths.set_data_dir(data_dir)
        paths.ensure_dirs()

        startup.mark("正在准备组件…", splash=splash, progress=0.35)
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

        # 图标要走 resource_dir()：打包之后 assets/ 在 _internal/（onedir）
        # 或 %TEMP%\_MEIxxxx（onefile）里，按 exe 目录找会找不到
        icon_path = paths.resource_dir() / "assets" / "icon.ico"
        if icon_path.exists():
            self.qt_app.setWindowIcon(QIcon(str(icon_path)))
        else:
            # 这条以前是静默的：打包版里路径不对时，界面照常起来，
            # 只是托盘与任务栏都没图标，事后很难查
            logger.warning("找不到程序图标，托盘/任务栏会没有图标：%s", icon_path)

        # ── 业务对象 ────────────────────────────────────────
        self.library = Library()
        self.library.load()

        # 音量均衡：后台响度分析（分析线程在第一次真正需要时才起）
        self.loudness = LoudnessService(self.config)
        self.player = PlayerEngine(self.config, self.library, self.loudness)
        # 恢复上次的播放队列与在播曲目。**必须在 QML 加载之前**：界面是在建立
        # 绑定的时候读一次属性值的，先把队列摆好，起来就是对的（见 restoreSession）。
        try:
            self.player.restoreSession()
        except Exception as e:
            logger.warning("恢复上次播放会话失败: %s", e)
        self.account = AccountManager(self.config)
        self.search = SearchController(self.config)
        self.library_bridge = LibraryController(self.config, self.library)
        self.discover = DiscoverController(self.config)
        self.artist = ArtistController(self)
        self.album = AlbumController(self)
        self.roam = RoamController(self.config, self.player, self)
        self.roam.watch_player()
        self.wiki = SongWikiController(self.player, self)
        self.wiki.watch_player()
        self.settings = SettingsController(self.config, self.loudness)
        self.app = AppController(self.config)
        # 自动更新：只负责检查与提示，真正的替换动作要用户点（见 bridges/update.py）
        self.updater = UpdateController(self.config)

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
        ctx.setContextProperty("artist", self.artist)
        ctx.setContextProperty("album", self.album)
        ctx.setContextProperty("roam", self.roam)
        ctx.setContextProperty("wiki", self.wiki)
        ctx.setContextProperty("settings", self.settings)
        ctx.setContextProperty("app", self.app)
        # 名字是 updater，**不要**改成 update：QML 里 `update` 会被窗口类型上
        # 的同名方法遮住（实测 SettingsWindow.qml 里 `update.xxx` 全是 undefined，
        # 而同一个 context 属性在别处读得到），改回去就会踩这个坑。
        ctx.setContextProperty("updater", self.updater)

        self.engine.warnings.connect(self._on_qml_warning)
        startup.mark("正在加载界面…", splash=splash, progress=0.55)

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
        self.artist.errorOccurred.connect(self.app.warn)
        self.album.errorOccurred.connect(self.app.warn)
        self.roam.errorOccurred.connect(self.app.warn)
        self.roam.message.connect(self.app.info)
        self.settings.message.connect(self.app.info)
        self.settings.errorOccurred.connect(self.app.error)
        # 音量均衡：分析线程只统计、不打扰（失败也只在日志里）
        self.loudness.changed.connect(self.settings.notifyLoudnessChanged)
        # 自动更新：检查结果、下载进度、失败原因都要让用户看见
        self.updater.message.connect(self.app.info)
        self.updater.errorOccurred.connect(self.app.error)

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
        # 逐字歌词开关：正在播的这首立刻跟上（没有真逐字就先补伪动态）
        try:
            self.player.applyLyricSettings()
        except Exception as e:
            logger.debug("应用歌词设置失败: %s", e)

    @Slot(str)
    def _on_fallback(self, source_id: str) -> None:
        from .sources import SOURCE_NAMES

        self.app.warn(f"当前音源不可用，已自动切换到 {SOURCE_NAMES.get(source_id, source_id)}")

    @Slot()
    def _on_remote_playlists(self) -> None:
        # 网易云歌单展示在「我的音乐」的左栏里
        self.library_bridge.setRemotePlaylists(self.account.remotePlaylists)

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

    # ── 启动画面 ────────────────────────────────────────────

    def _watch_first_frame(self) -> None:
        """首帧一到就撤启动画面。

        用 ``frameSwapped`` 而不是窗口 ``visible``：QML 窗口在 ``engine.load`` 里
        就已经 show 了，但那一刻场景图还没画出来 —— 此时撤画面会闪一下空窗口。
        信号在第一次触发后就断开（它每帧都发，留着等于给每帧加一次 Python 调用）；
        Qt 万一没发信号（比如窗口被系统挡在最小化状态），有 8 秒兜底。
        """
        splash = self.splash
        if splash is None:
            return
        try:
            self._frame_window = self.engine.rootObjects()[0]
            self._frame_window.frameSwapped.connect(self._finish_splash)
        except Exception as e:
            logger.debug("接首帧信号失败，改用兜底计时收启动画面: %s", e)
        QTimer.singleShot(8000, self._finish_splash)

    @Slot()
    def _finish_splash(self) -> None:
        """可重复调用：第一次就把画面交出去淡出，之后是空操作。"""
        splash, self.splash = self.splash, None
        if splash is None:
            return
        window, self._frame_window = getattr(self, "_frame_window", None), None
        if window is not None:
            try:
                window.frameSwapped.disconnect(self._finish_splash)
            except Exception:
                pass
        startup.mark("首帧已渲染")
        startup.report()
        splash.finish()

    # ── 启动 ────────────────────────────────────────────────

    def run(self) -> int:
        # 打包版排查问题时的第一手信息：资源住在 _internal / _MEIxxxx 里，
        # 数据住在 exe 旁边或 %LOCALAPPDATA%，这两者不是一回事
        logger.info(
            "目录：程序=%s 资源=%s 数据=%s",
            paths.program_dir(), paths.resource_dir(), paths.data_dir(),
        )

        main_qml = paths.qml_dir() / "Main.qml"
        if not main_qml.exists():
            logger.error("找不到界面文件: %s", main_qml)
            self._finish_splash()
            return 2

        # requests（0.4 秒）已经不在启动链上了（见 app/lazy.py），这里让它在
        # 后台线程里先导进来。**必须放在 engine.load 之前、构造之后**：QML 编译
        # 那 1 秒主线程几乎都在 C++ 里（GIL 是空的），放这儿基本白捡；而构造阶段
        # 是纯 Python，放在那儿两边会抢 GIL，反而把构造拖慢一倍（实测 150→690 ms）。
        # 恢复会话要建网易云音源（requests.Session），它必须在那之前导完。
        prewarm("requests")

        self.engine.load(QUrl.fromLocalFile(str(main_qml)))
        if not self.engine.rootObjects():
            logger.error("QML 加载失败，请查看上方告警")
            self._finish_splash()  # 失败也要收掉画面，否则它会一直压在最上层
            return 3

        startup.mark("正在恢复播放会话…", splash=self.splash, progress=0.90)
        self._watch_first_frame()
        self._apply_source_prefs()
        self.account.restore()
        # 界面起来之后再挂自动更新：启动时的取数据优先
        self.updater.start()

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
            self.loudness.shutdown()
        except Exception as e:
            logger.debug("关闭响度分析服务失败: %s", e)
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

def main(argv=None, data_dir: Optional[str] = None, splash=None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if data_dir is None:
        # 兼容直接调 application.main 的调用方（tests/、工具脚本）；
        # 走 main.py 时它已经解析过并把结果传进来了。
        data_dir = paths.pop_data_dir_arg(argv)
    app = Application(argv, data_dir=data_dir, splash=splash)
    return app.run()
