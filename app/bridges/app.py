"""应用级控制器：导航状态、通知、窗口状态、剪贴板。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .. import paths
from ..sources import SOURCE_META

logger = logging.getLogger(__name__)

PAGES: List[Dict[str, str]] = [
    {"id": "discover", "name": "发现音乐", "icon": "Globe", "desc": "推荐歌单与排行榜"},
    {"id": "search", "name": "搜索", "icon": "Search", "desc": "多音源在线搜索"},
    {"id": "library", "name": "我的音乐", "icon": "Heart", "desc": "我喜欢与歌单"},
    {"id": "local", "name": "本地音乐", "icon": "Folder", "desc": "扫描本地曲库"},
    {"id": "queue", "name": "播放队列", "icon": "List", "desc": "当前播放列表"},
]


class AppController(QObject):
    pageChanged = Signal()
    expandedChanged = Signal()
    queuePanelChanged = Signal()
    notify = Signal(str, str)   # level, message
    sourceMetaChanged = Signal()
    loginRequested = Signal()
    settingsRequested = Signal()
    systemDarkChanged = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._page = "discover"
        self._expanded = bool(config.get("window.player_expanded", False))
        self._queue_panel = bool(config.get("window.queue_visible", False))

        # 跟随系统深浅色：FluThemeType 没有 Auto，需要我们自己读取系统配色
        try:
            hints = QGuiApplication.styleHints()
            hints.colorSchemeChanged.connect(self.systemDarkChanged)
        except Exception as e:  # pragma: no cover
            logger.debug("无法监听系统配色变化: %s", e)

    @Property(bool, notify=systemDarkChanged)
    def systemDark(self) -> bool:  # noqa: N802
        try:
            from PySide6.QtCore import Qt

            return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            return False

    # ── 导航 ────────────────────────────────────────────────

    @Property("QVariantList", constant=True)
    def pages(self):  # noqa: N802
        return PAGES

    @Property(str, notify=pageChanged)
    def page(self) -> str:
        return self._page

    @Slot(str)
    def go(self, page_id: str) -> None:
        page_id = str(page_id or "").strip()
        if not page_id or page_id == self._page:
            return
        self._page = page_id
        self.pageChanged.emit()

    # ── 展开态 / 队列面板 ───────────────────────────────────

    @Property(bool, notify=expandedChanged)
    def expanded(self) -> bool:
        return self._expanded

    @Slot()
    def toggleExpanded(self) -> None:  # noqa: N802
        self._expanded = not self._expanded
        self._config.set("window.player_expanded", self._expanded)
        self.expandedChanged.emit()

    @Slot(bool)
    def setExpanded(self, value: bool) -> None:  # noqa: N802
        if bool(value) == self._expanded:
            return
        self._expanded = bool(value)
        self._config.set("window.player_expanded", self._expanded)
        self.expandedChanged.emit()

    @Property(bool, notify=queuePanelChanged)
    def queuePanel(self) -> bool:  # noqa: N802
        return self._queue_panel

    @Slot()
    def toggleQueuePanel(self) -> None:  # noqa: N802
        self._queue_panel = not self._queue_panel
        self._config.set("window.queue_visible", self._queue_panel)
        self.queuePanelChanged.emit()

    # ── 通知 ────────────────────────────────────────────────

    @Slot(str)
    def info(self, message: str) -> None:
        self.notify.emit("info", str(message))

    @Slot()
    def openLogin(self) -> None:  # noqa: N802
        self.loginRequested.emit()

    @Slot()
    def openSettings(self) -> None:  # noqa: N802
        self.settingsRequested.emit()

    @Slot(str)
    def success(self, message: str) -> None:
        self.notify.emit("success", str(message))

    @Slot(str)
    def warn(self, message: str) -> None:
        self.notify.emit("warning", str(message))

    @Slot(str)
    def error(self, message: str) -> None:
        self.notify.emit("error", str(message))

    # ── 信息 ────────────────────────────────────────────────

    @Property(str, constant=True)
    def version(self) -> str:
        from ..paths import APP_VERSION

        return APP_VERSION

    @Property(str, constant=True)
    def appName(self) -> str:  # noqa: N802
        from ..paths import APP_DISPLAY_NAME

        return APP_DISPLAY_NAME

    @Property(str, constant=True)
    def dataDir(self) -> str:  # noqa: N802
        return str(paths.data_dir())

    @Property("QVariantList", constant=True)
    def sources(self):  # noqa: N802
        return [dict(m) for m in SOURCE_META]

    # ── 窗口状态 ────────────────────────────────────────────

    @Slot(int, int)
    def saveWindowSize(self, width: int, height: int) -> None:  # noqa: N802
        self._config.set("window.width", int(width), autosave=False)
        self._config.set("window.height", int(height))

    @Slot(bool)
    def saveMaximized(self, value: bool) -> None:  # noqa: N802
        self._config.set("window.maximized", bool(value))

    @Slot(result=bool)
    def restoreMaximized(self) -> bool:  # noqa: N802
        return bool(self._config.get("window.maximized", False))

    @Slot(result=int)
    def initialWidth(self) -> int:  # noqa: N802
        try:
            return max(940, int(self._config.get("window.width", 1180) or 1180))
        except (TypeError, ValueError):
            return 1180

    @Slot(result=int)
    def initialHeight(self) -> int:  # noqa: N802
        try:
            return max(620, int(self._config.get("window.height", 760) or 760))
        except (TypeError, ValueError):
            return 760

    @Slot(str, "QVariant")
    def savePref(self, key: str, value: Any) -> None:  # noqa: N802
        self._config.set(str(key), value)

    @Slot(str, "QVariant", result="QVariant")
    def loadPref(self, key: str, default: Any = None):  # noqa: N802
        return self._config.get(str(key), default)

    @Slot()
    def flush(self) -> None:
        self._config.save()
