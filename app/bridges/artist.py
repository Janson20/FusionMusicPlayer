"""歌手页控制器：点任意位置的歌手名打开，展示歌手信息与热门歌曲。

歌手名可能来自任何音源（QQ / 酷我 / 酷狗 / 咪咕 / 本地文件标签），它们都没有
网易云的歌手 id，所以这里统一**按名字定位**歌手：先搜同名歌手，再用详情接口
取热门歌曲。搜索置顶卡片那种已经拿到 id 的入口直接走 id，省一次搜索。
"""

from __future__ import annotations

import logging
import threading
from typing import Dict

from PySide6.QtCore import QObject, Property, Signal, Slot

from ..core.models import Track, TrackListModel
from ..sources import netease

logger = logging.getLogger(__name__)

class _Emitter(QObject):
    loaded = Signal(int, object)

class ArtistController(QObject):
    """歌手详情页的数据与开关状态。"""

    changed = Signal()
    errorOccurred = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._emitter = _Emitter(self)
        self._emitter.loaded.connect(self._on_loaded)

        self._hot_model = TrackListModel()
        self._meta: Dict = {}
        self._opened = False
        self._loading = False
        self._seq = 0

    # ── 属性 ────────────────────────────────────────────────

    @Property(QObject, constant=True)
    def hotModel(self):  # noqa: N802
        return self._hot_model

    @Property(bool, notify=changed)
    def opened(self) -> bool:
        return self._opened

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def artistId(self) -> str:  # noqa: N802
        return str(self._meta.get("id") or "")

    @Property(str, notify=changed)
    def artistName(self) -> str:  # noqa: N802
        return str(self._meta.get("name") or "")

    @Property("QVariant", notify=changed)
    def meta(self):  # noqa: N802
        return dict(self._meta)

    # ── 打开 / 关闭 ─────────────────────────────────────────

    @Slot(str, str)
    def openArtist(self, artist_id: str, name: str = "") -> None:  # noqa: N802
        """已经有歌手 id 时走这里（搜索置顶卡片）。"""
        self._open(str(artist_id or ""), str(name or ""))

    @Slot(str)
    def openByName(self, name: str) -> None:  # noqa: N802
        """只有歌手名时走这里（列表行 / 播放栏 / 展开播放页）。"""
        self._open("", str(name or ""))

    @Slot()
    def close(self) -> None:
        self._seq += 1
        self._opened = False
        self._loading = False
        self._meta = {}
        self._hot_model.clear()
        self.changed.emit()

    def _open(self, artist_id: str, name: str) -> None:
        artist_id = artist_id.strip()
        name = name.strip()
        if not artist_id and not name:
            return
        self._seq += 1
        seq = self._seq
        # 先让面板以「加载中」的样子出现，名字先用调用方给的那个
        self._opened = True
        self._loading = True
        self._meta = {"id": artist_id, "name": name}
        self._hot_model.clear()
        self.changed.emit()
        threading.Thread(
            target=self._worker, args=(seq, artist_id, name), daemon=True, name="artist"
        ).start()

    def _worker(self, seq: int, artist_id: str, name: str) -> None:
        try:
            page = netease.artist_page(artist_id, name)
        except Exception as e:
            logger.debug("歌手页加载失败: %s", e)
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
            self._hot_model.clear()
            self.changed.emit()
            self.errorOccurred.emit(
                f"没找到歌手「{wanted}」" if wanted else "歌手信息加载失败，请稍后重试"
            )
            return

        payload = dict(page)
        hot = payload.pop("hot_songs", []) or []
        self._meta = payload
        self._hot_model.set_tracks([Track.from_music_info(mi) for mi in hot])
        self.changed.emit()
        if not hot:
            self.errorOccurred.emit(f"「{self.artistName}」暂时没有可播放的歌曲")
