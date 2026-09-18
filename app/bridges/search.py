"""多音源搜索控制器。"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List

from PySide6.QtCore import QObject, Property, Signal, Slot

from ..core.models import Track, TrackListModel
from ..sources import SOURCE_META, SOURCE_NAMES, search_all

logger = logging.getLogger(__name__)

class _Emitter(QObject):
    done = Signal(int, object)
    suggestions = Signal(int, object)

class SearchController(QObject):
    """并发搜索全部音源，并把结果按来源分页展示。"""

    resultsChanged = Signal()
    loadingChanged = Signal()
    errorOccurred = Signal(str)
    sourceChanged = Signal()
    historyChanged = Signal()
    suggestionsChanged = Signal()

    MAX_HISTORY = 24

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._emitter = _Emitter(self)
        self._emitter.done.connect(self._on_done)
        self._emitter.suggestions.connect(self._on_suggestions)

        self._model = TrackListModel()
        self._loading = False
        self._keyword = ""
        self._page = 1
        self._seq = 0
        self._current_source = "all"
        self._last_page_size = 20
        self._by_source: Dict[str, List[Track]] = {}
        self._totals: Dict[str, int] = {}
        self._history: List[str] = list(config.get("search_history", []) or [])
        self._suggestions: List[str] = []
        self._has_more = False

    # ── 属性 ────────────────────────────────────────────────

    @Property(QObject, constant=True)
    def model(self):
        return self._model

    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=resultsChanged)
    def keyword(self) -> str:
        return self._keyword

    @Property(int, notify=resultsChanged)
    def page(self) -> int:
        return self._page

    @Property(str, notify=sourceChanged)
    def currentSource(self) -> str:  # noqa: N802
        return self._current_source

    @Property(int, notify=resultsChanged)
    def resultCount(self) -> int:  # noqa: N802
        return self._model.length()

    @Property(bool, notify=resultsChanged)
    def hasResults(self) -> bool:  # noqa: N802
        return self._model.length() > 0

    @Property(bool, notify=resultsChanged)
    def hasMore(self) -> bool:  # noqa: N802
        return self._has_more

    @Property("QVariantList", notify=historyChanged)
    def history(self):  # noqa: N802
        return list(self._history)

    @Property("QVariantList", notify=suggestionsChanged)
    def suggestions(self):  # noqa: N802
        return list(self._suggestions)

    @Property("QVariantList", notify=sourceChanged)
    def sourceTabs(self):  # noqa: N802
        tabs = [{"id": "all", "name": "全部", "count": self._total_count()}]
        for meta in SOURCE_META:
            sid = meta["id"]
            if sid not in self._by_source or not self._by_source[sid]:
                continue
            tabs.append(
                {"id": sid, "name": meta["short"], "count": len(self._by_source[sid])}
            )
        return tabs

    def _total_count(self) -> int:
        return sum(len(v) for v in self._by_source.values())

    # ── 搜索 ────────────────────────────────────────────────

    @Slot(str)
    def search(self, keyword: str) -> None:  # noqa: A003
        keyword = (keyword or "").strip()
        if not keyword:
            self.errorOccurred.emit("请输入搜索关键词")
            return
        self._keyword = keyword
        self._page = 1
        self._push_history(keyword)
        self._run()

    @Slot()
    def nextPage(self) -> None:  # noqa: N802
        if not self._keyword or self._loading:
            return
        self._page += 1
        self._run()

    @Slot()
    def prevPage(self) -> None:  # noqa: N802
        if not self._keyword or self._loading or self._page <= 1:
            return
        self._page -= 1
        self._run()

    @Slot(str)
    def setSource(self, source_id: str) -> None:  # noqa: N802
        self._current_source = source_id or "all"
        self._apply_filter()
        self.sourceChanged.emit()

    @Slot()
    def retry(self) -> None:
        if self._keyword:
            self._run()

    @Slot()
    def clear(self) -> None:
        self._seq += 1
        self._keyword = ""
        self._page = 1
        self._by_source.clear()
        self._totals.clear()
        self._model.clear()
        self._has_more = False
        self._loading = False
        self.loadingChanged.emit()
        self.resultsChanged.emit()
        self.sourceChanged.emit()

    @Slot(str)
    def removeHistory(self, keyword: str) -> None:  # noqa: N802
        if keyword in self._history:
            self._history.remove(keyword)
            self._config.set("search_history", self._history)
            self.historyChanged.emit()

    @Slot()
    def clearHistory(self) -> None:  # noqa: N802
        self._history.clear()
        self._config.set("search_history", [])
        self.historyChanged.emit()

    def _push_history(self, keyword: str) -> None:
        if keyword in self._history:
            self._history.remove(keyword)
        self._history.insert(0, keyword)
        del self._history[self.MAX_HISTORY:]
        self._config.set("search_history", self._history)
        self.historyChanged.emit()

    def _run(self) -> None:
        self._seq += 1
        seq = self._seq
        page = self._page
        keyword = self._keyword

        self._loading = True
        self.loadingChanged.emit()
        threading.Thread(
            target=self._worker, args=(seq, keyword, page), daemon=True, name="search"
        ).start()

    def _worker(self, seq: int, keyword: str, page: int) -> None:
        try:
            enabled = self._config.get("sources.enabled", None)
            ids = None
            if isinstance(enabled, list) and enabled:
                ids = [s for s in enabled if s in SOURCE_NAMES]
            groups = search_all(keyword, page=page, limit=20, source_ids=ids)
        except Exception as e:
            logger.exception("搜索失败")
            groups = []
            self._emitter.done.emit(seq, {"error": str(e)})
            return
        self._emitter.done.emit(seq, {"groups": groups, "page": page})

    @Slot(int, object)
    def _on_done(self, seq: int, payload) -> None:
        if seq != self._seq:
            return
        self._loading = False
        self.loadingChanged.emit()

        if not isinstance(payload, dict) or "groups" not in payload:
            self.errorOccurred.emit("搜索失败，请检查网络连接")
            return

        page = int(payload.get("page") or 1)
        groups = payload.get("groups") or []
        self._by_source.clear()
        self._totals.clear()
        any_total = 0
        for g in groups:
            sid = g.get("source") or ""
            tracks = [Track.from_music_info(mi) for mi in (g.get("results") or [])]
            if sid and tracks:
                self._by_source[sid] = tracks
                total = int(g.get("total") or 0)
                self._totals[sid] = total
                any_total = max(any_total, total)

        self._last_page_size = 20
        if any_total > 0:
            self._has_more = page * self._last_page_size < any_total
        else:
            # 接口不提供总数时，只要还有任意音源返回满页就认为可能有下一页
            self._has_more = any(len(v) >= 15 for v in self._by_source.values())

        self._apply_filter()
        self.resultsChanged.emit()
        self.sourceChanged.emit()

        if not self._by_source:
            self.errorOccurred.emit(f"没有找到「{self._keyword}」的相关结果")

    def _apply_filter(self) -> None:
        if self._current_source == "all":
            merged: List[Track] = []
            for meta in SOURCE_META:
                merged.extend(self._by_source.get(meta["id"], []))
            # 网易云优先已在 sourceTabs 顺序里体现；「全部」页按音源顺序拼接
            self._model.set_tracks(merged)
        else:
            self._model.set_tracks(self._by_source.get(self._current_source, []))

    # ── 搜索建议（来自本地历史 + 热搜） ─────────────────────

    @Slot(str)
    def suggest(self, text: str) -> None:
        text = (text or "").strip().lower()
        if not text:
            self._suggestions = []
            self.suggestionsChanged.emit()
            return
        hits = [h for h in self._history if text in h.lower()][:8]
        self._suggestions = hits
        self.suggestionsChanged.emit()

    @Slot(object)
    def _on_suggestions(self, items) -> None:
        self._suggestions = list(items or [])
        self.suggestionsChanged.emit()

    @Slot(str, int, result="QVariant")
    def resultAt(self, source_id: str, index: int):  # noqa: N802
        tracks = self._by_source.get(source_id) or []
        if 0 <= index < len(tracks):
            return tracks[index].to_dict()
        return None
