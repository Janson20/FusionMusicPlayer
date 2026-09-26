"""应用级控制器：导航状态、通知、窗口状态、剪贴板。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .. import paths
from ..sources import SOURCE_META

logger = logging.getLogger(__name__)

# ── 窗口尺寸 ────────────────────────────────────────────────
# 默认尺寸是照 1080p 定的舒适值，但**不能顶出屏幕**：1366×768 上任务栏一占，
# 可用高度只剩 728，760 的窗口会把底部播放栏顶到屏幕外面、点都点不到；
# 1366×768 开 125% 缩放更极端（可用区域只有 1093×582，比窗口的最小高度还矮）。
# 所以初始尺寸与最小尺寸都要夹进**屏幕可用区域**（不是整块屏幕）。
WINDOW_DEFAULT_W = 1180
WINDOW_DEFAULT_H = 760
#: 窗口本身能缩到多小（布局的下限，与 Main.qml 里的两个常量没有第二个来源）
WINDOW_FLOOR_W = 880
WINDOW_FLOOR_H = 560
#: 与屏幕边缘留的缝（左右各半、上下各半）
SCREEN_MARGIN = 48


def fit_window(want: int, available: int, floor: int, margin: int = SCREEN_MARGIN) -> int:
    """把窗口尺寸夹进「屏幕可用区域 − 边距」（纯函数，便于离线测试）。

    * ``available <= 0``（拿不到屏幕信息，比如没有显示器）→ 只保证不小于 ``floor``；
    * 屏幕比 ``floor`` 还小时**底线让位给屏幕**：最小值本身把窗口撑出屏幕，
      比尺寸偏大更难用（那种情况下用户连边框都拖不到）。
    """
    try:
        want = int(want)
        available = int(available)
        floor = int(floor)
    except (TypeError, ValueError):
        return WINDOW_DEFAULT_W
    if available <= 0:
        return max(floor, want)
    limit = max(1, available - max(0, int(margin)))
    return max(min(floor, limit), min(want, limit))

PAGES: List[Dict[str, str]] = [
    {"id": "discover", "name": "发现音乐", "icon": "Globe", "desc": "推荐歌单与排行榜"},
    {"id": "roam", "name": "漫游", "icon": "MapCompassTop", "desc": "按口味持续推荐的流"},
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

    def _available_size(self) -> Tuple[int, int]:
        """主屏可用区域（已排除任务栏）的逻辑像素尺寸；拿不到返回 ``(0, 0)``。"""
        try:
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                return int(geo.width()), int(geo.height())
        except Exception as e:  # pragma: no cover - 依赖运行环境
            logger.debug("读取屏幕可用区域失败: %s", e)
        return 0, 0

    def _read_size(self, key: str, default: int) -> int:
        try:
            return int(self._config.get(key, default) or default)
        except (TypeError, ValueError):
            return int(default)

    @Slot(result=int)
    def minimumWidth(self) -> int:  # noqa: N802
        """窗口最小宽度。屏幕比它还窄时跟着屏幕缩 —— 否则最小值自己就把窗口顶出屏幕。"""
        return fit_window(WINDOW_FLOOR_W, self._available_size()[0], WINDOW_FLOOR_W)

    @Slot(result=int)
    def minimumHeight(self) -> int:  # noqa: N802
        return fit_window(WINDOW_FLOOR_H, self._available_size()[1], WINDOW_FLOOR_H)

    @Slot(result=int)
    def initialWidth(self) -> int:  # noqa: N802
        return fit_window(
            self._read_size("window.width", WINDOW_DEFAULT_W),
            self._available_size()[0],
            self.minimumWidth(),
        )

    @Slot(result=int)
    def initialHeight(self) -> int:  # noqa: N802
        return fit_window(
            self._read_size("window.height", WINDOW_DEFAULT_H),
            self._available_size()[1],
            self.minimumHeight(),
        )

    @Slot(int, int, int, int, result="QVariant")
    def fitWindow(self, want_w: int, want_h: int, floor_w: int, floor_h: int):  # noqa: N802
        """把任意窗口的「想要的尺寸 + 下限」夹进屏幕（设置 / 登录窗口用）。

        返回 ``{"width", "height"}``；QML 侧同时把它当作 minimumWidth/minimumHeight
        的来源 —— 低分辨率下**下限必须一起让位**，否则窗口被自己的最小值顶出屏幕。
        """
        avail_w, avail_h = self._available_size()
        w = fit_window(want_w, avail_w, floor_w)
        h = fit_window(want_h, avail_h, floor_h)
        return {"width": min(w, max(1, avail_w)) if avail_w > 0 else w,
                "height": min(h, max(1, avail_h)) if avail_h > 0 else h}

    @Slot(str, "QVariant")
    def savePref(self, key: str, value: Any) -> None:  # noqa: N802
        self._config.set(str(key), value)

    @Slot(str, "QVariant", result="QVariant")
    def loadPref(self, key: str, default: Any = None):  # noqa: N802
        return self._config.get(str(key), default)

    @Slot()
    def flush(self) -> None:
        self._config.save()
