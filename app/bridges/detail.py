"""详情页控制器基类：歌手页 / 专辑页（以后还有别的）共用的那套开关与加载逻辑。

页面之间的差别只有三件事：**从哪拿数据**、**列表放在哪个字段**、**文案里叫它什么**。
其它（打开中状态、请求序号防串台、模型装载、找不到时的提示）完全一样，
所以放在这里；子类只需要实现 :meth:`_fetch`。

「按名字打开」是刻意的设计：QQ / 酷我 / 酷狗 / 咪咕 / 本地文件里的曲目都没有
网易云的歌手 / 专辑 id，只能拿名字去搜，搜到之后再用详情接口取权威数据。
"""

from __future__ import annotations

import logging
import threading
from typing import Dict

from PySide6.QtCore import QObject, Property, Signal, Slot

from ..core.models import Track, TrackListModel

logger = logging.getLogger(__name__)

class _Emitter(QObject):
    loaded = Signal(int, object)

class DetailPageController(QObject):
    """覆盖层详情页的数据与开关状态。"""

    changed = Signal()
    errorOccurred = Signal(str)

    #: 文案里的名词（「没找到歌手 xxx」）；子类覆盖
    noun = "详情"
    #: ``_fetch`` 返回的字典里，哪个字段是曲目列表
    list_key = "tracks"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._emitter = _Emitter(self)
        self._emitter.loaded.connect(self._on_loaded)

        self._model = TrackListModel()
        self._meta: Dict = {}
        self._opened = False
        self._loading = False
        self._seq = 0

    # ── 属性 ────────────────────────────────────────────────

    @Property(QObject, constant=True)
    def model(self):
        """页面里的曲目列表。"""
        return self._model

    @Property(bool, notify=changed)
    def opened(self) -> bool:
        return self._opened

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def pageId(self) -> str:  # noqa: N802
        return str(self._meta.get("id") or "")

    @Property(str, notify=changed)
    def pageTitle(self) -> str:  # noqa: N802
        return str(self._meta.get("name") or "")

    @Property("QVariant", notify=changed)
    def meta(self):  # noqa: N802
        return dict(self._meta)

    # ── 打开 / 关闭 ─────────────────────────────────────────

    @Slot(str, str)
    def openById(self, page_id: str, name: str = "") -> None:  # noqa: N802
        """已经有 id 时走这里（列表行、搜索结果卡片）。"""
        self._open(str(page_id or ""), str(name or ""))

    @Slot(str)
    def openByName(self, name: str) -> None:  # noqa: N802
        """只有名字时走这里（其它音源的曲目、本地文件标签）。"""
        self._open("", str(name or ""))

    @Slot()
    def close(self) -> None:
        self._seq += 1
        self._opened = False
        self._loading = False
        self._meta = {}
        self._model.clear()
        self.changed.emit()

    def _open(self, page_id: str, name: str) -> None:
        page_id = page_id.strip()
        name = name.strip()
        if not page_id and not name:
            return
        self._seq += 1
        seq = self._seq
        # 先让面板以「加载中」的样子出现，名字先用调用方给的那个
        self._opened = True
        self._loading = True
        self._meta = {"id": page_id, "name": name}
        self._model.clear()
        self.changed.emit()
        self._start(seq, page_id, name)

    def _start(self, seq: int, page_id: str, name: str) -> None:
        threading.Thread(
            target=self._worker, args=(seq, page_id, name), daemon=True,
            name=f"{self.__class__.__name__.lower()}-load",
        ).start()

    def _worker(self, seq: int, page_id: str, name: str) -> None:
        try:
            page = self._fetch(page_id, name)
        except Exception as e:
            logger.debug("%s 加载失败: %s", self.noun, e)
            page = {}
        self._emitter.loaded.emit(seq, page)

    @Slot(int, object)
    def _on_loaded(self, seq: int, page) -> None:
        if seq != self._seq:
            return
        self._loading = False
        if not isinstance(page, dict) or not page:
            wanted = str(self._meta.get("name") or "").strip()
            self._opened = False
            self._meta = {}
            self._model.clear()
            self.changed.emit()
            self.errorOccurred.emit(
                f"没找到{self.noun}「{wanted}」" if wanted else f"{self.noun}信息加载失败，请稍后重试"
            )
            return

        payload = dict(page)
        tracks = payload.pop(self.list_key, []) or []
        self._meta = payload
        self._model.set_tracks([Track.from_music_info(mi) for mi in tracks])
        self.changed.emit()
        if not tracks:
            self.errorOccurred.emit(f"「{self.pageTitle}」暂时没有可播放的歌曲")

    # ── 子类实现 ────────────────────────────────────────────

    def _fetch(self, page_id: str, name: str) -> Dict:
        """取回页面数据（曲目列表放在 :attr:`list_key` 字段里）。"""
        raise NotImplementedError
