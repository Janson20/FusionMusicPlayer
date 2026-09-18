"""音乐库控制器：歌单 / 我喜欢 / 历史 / 本地音乐。"""

from __future__ import annotations

import logging
import os
import threading
from typing import Dict, List

from PySide6.QtCore import QObject, Property, Signal, Slot

from ..core.models import Track, TrackListModel
from ..core.resolver import AUDIO_EXTENSIONS, resolve_local_metadata, scan_local_folder
from ..core.store import (
    FAVORITES_ID,
    HISTORY_ID,
    SORT_LABELS,
    Library,
    name_sort_key,
)

logger = logging.getLogger(__name__)


class _Emitter(QObject):
    scanProgress = Signal(object)
    scanDone = Signal(object)
    remoteTracks = Signal(object)


class LibraryController(QObject):
    """统一暴露本地音乐数据给 QML。"""

    playlistsChanged = Signal()
    tracksChanged = Signal()
    favoritesChanged = Signal()
    historyChanged = Signal()
    localChanged = Signal()
    scanningChanged = Signal()
    remoteChanged = Signal()
    message = Signal(str)
    errorOccurred = Signal(str)
    selectionChanged = Signal()

    REMOTE_PREFIX = "wy:"

    def __init__(self, config, library: Library, parent=None):
        super().__init__(parent)
        self._config = config
        self._library = library
        self._emitter = _Emitter(self)
        self._emitter.scanDone.connect(self._on_scan_done)
        self._emitter.scanProgress.connect(self._on_scan_progress)
        self._emitter.remoteTracks.connect(self._on_remote_tracks)

        self._tracks_model = TrackListModel()
        self._favorites_model = TrackListModel()
        self._history_model = TrackListModel()
        self._local_model = TrackListModel()

        self._selected_id: str = ""
        self._selected_name: str = ""
        self._scanning = False
        self._scan_total = 0
        self._scan_done = 0

        # 网易云歌单（内存态，不落盘）
        self._remote: List[Dict] = []
        self._remote_cache: Dict[str, List[Track]] = {}
        self._remote_loading = False

        self._library.add_listener(self._on_library_event)
        self.refresh_all()

    # ── 属性 ────────────────────────────────────────────────

    @Property(QObject, constant=True)
    def tracksModel(self):  # noqa: N802
        return self._tracks_model

    @Property(QObject, constant=True)
    def favoritesModel(self):  # noqa: N802
        return self._favorites_model

    @Property(QObject, constant=True)
    def historyModel(self):  # noqa: N802
        return self._history_model

    @Property(QObject, constant=True)
    def localModel(self):  # noqa: N802
        return self._local_model

    @Property("QVariantList", notify=playlistsChanged)
    def playlists(self):  # noqa: N802
        out = [
            {
                "id": FAVORITES_ID,
                "name": "我喜欢的音乐",
                "count": self._favorites_model.length(),
                "system": True,
                "icon": "Heart",
            },
            {
                "id": HISTORY_ID,
                "name": "最近播放",
                "count": self._history_model.length(),
                "system": True,
                "icon": "History",
            },
            {
                "id": "__local__",
                "name": "本地音乐",
                "count": self._local_model.length(),
                "system": True,
                "icon": "Folder",
            },
        ]
        for pl in self._library.playlists():
            out.append(
                {
                    "id": pl.id,
                    "name": pl.name,
                    "count": pl.count,
                    "system": False,
                    "icon": "List",
                }
            )
        return out

    @Property(str, notify=selectionChanged)
    def selectedId(self) -> str:  # noqa: N802
        return self._selected_id

    @Property(str, notify=selectionChanged)
    def selectedName(self) -> str:  # noqa: N802
        if self._selected_name:
            return self._selected_name
        for p in self.playlists:
            if p["id"] == self._selected_id:
                return str(p["name"])
        return ""

    @Property(bool, notify=selectionChanged)
    def selectedIsRemote(self) -> bool:  # noqa: N802
        return self._selected_id.startswith(self.REMOTE_PREFIX)

    @Property(bool, notify=remoteChanged)
    def remoteLoading(self) -> bool:  # noqa: N802
        return self._remote_loading

    @Property("QVariantList", notify=remoteChanged)
    def remotePlaylists(self):  # noqa: N802
        """登录用户的网易云歌单（含「我喜欢的音乐」）。"""
        return list(self._remote)

    @Property(int, notify=tracksChanged)
    def selectedCount(self) -> int:  # noqa: N802
        # 注意 notify 用 tracksChanged 而不是 selectionChanged：
        # 网易云歌单是异步拉取的，曲目到达时只会触发 tracksChanged
        return self._tracks_model.length()

    @Property(bool, notify=scanningChanged)
    def scanning(self) -> bool:
        return self._scanning

    @Property(int, notify=scanningChanged)
    def scanProgress(self) -> int:  # noqa: N802
        if not self._scan_total:
            return 0
        return int(self._scan_done * 100 / self._scan_total)

    @Property("QVariantList", constant=True)
    def sortModes(self):  # noqa: N802
        return [{"id": k, "name": v} for k, v in SORT_LABELS.items()]

    @Property("QVariantList", notify=localChanged)
    def localFolders(self):  # noqa: N802
        return list(self._config.get("local.folders", []) or [])

    # ── 选中与刷新 ──────────────────────────────────────────

    @Slot(str)
    def select(self, playlist_id: str) -> None:
        playlist_id = playlist_id or ""
        if playlist_id.startswith(self.REMOTE_PREFIX):
            self.selectRemote(playlist_id[len(self.REMOTE_PREFIX):])
            return
        self._selected_id = playlist_id
        self._selected_name = ""
        self._reload_tracks()
        self.selectionChanged.emit()

    # ── 网易云歌单 ──────────────────────────────────────────

    @Slot(object)
    def setRemotePlaylists(self, items) -> None:
        """由 AccountManager 推送登录用户的歌单列表。"""
        out: List[Dict] = []
        for item in items or []:
            try:
                out.append(
                    {
                        "id": str(item.get("id") or ""),
                        "name": str(item.get("name") or ""),
                        "count": int(item.get("track_count") or 0),
                        "cover": str(item.get("cover_url") or ""),
                        "system": False,
                        "remote": True,
                        "icon": "Cloud",
                    }
                )
            except Exception:
                continue
        self._remote = [x for x in out if x["id"]]
        # 歌单列表变了，缓存的曲目可能已过期
        self._remote_cache.clear()
        self.remoteChanged.emit()

    @Slot(str, str)
    def selectRemote(self, playlist_id: str, name: str = "") -> None:  # noqa: N802
        """选中某个网易云歌单，异步拉取其曲目。"""
        playlist_id = str(playlist_id or "")
        if not playlist_id:
            return
        self._selected_id = self.REMOTE_PREFIX + playlist_id
        self._selected_name = name or self._name_of_remote(playlist_id)
        self.selectionChanged.emit()

        cached = self._remote_cache.get(playlist_id)
        if cached is not None:
            self._tracks_model.set_tracks(cached)
            self.tracksChanged.emit()
            return

        self._tracks_model.clear()
        self._remote_loading = True
        self.tracksChanged.emit()
        self.remoteChanged.emit()
        threading.Thread(
            target=self._remote_worker, args=(playlist_id,), daemon=True, name="wy-playlist"
        ).start()

    def _name_of_remote(self, playlist_id: str) -> str:
        for p in self._remote:
            if p["id"] == playlist_id:
                return str(p["name"])
        return "网易云歌单"

    def _remote_worker(self, playlist_id: str) -> None:
        tracks: List[Track] = []
        error = ""
        try:
            from ..sources import netease

            infos = netease.playlist_tracks(playlist_id)
            tracks = [Track.from_music_info(mi) for mi in (infos or [])]
        except Exception as e:
            logger.warning("拉取网易云歌单失败 (%s): %s", playlist_id, e)
            error = str(e)
        self._emitter.remoteTracks.emit((playlist_id, tracks, error))

    @Slot(object)
    def _on_remote_tracks(self, payload) -> None:
        playlist_id, tracks, error = payload
        self._remote_loading = False
        self.remoteChanged.emit()

        if not error:
            self._remote_cache[playlist_id] = list(tracks)

        # 期间用户可能已经切走了
        if self._selected_id != self.REMOTE_PREFIX + playlist_id:
            return

        self._tracks_model.set_tracks(tracks)
        self.tracksChanged.emit()
        if error:
            self.errorOccurred.emit(f"拉取歌单失败：{error}")
        elif not tracks:
            self.message.emit("这个歌单没有可显示的歌曲")

    def _reload_tracks(self) -> None:
        pid = self._selected_id
        if pid == FAVORITES_ID:
            self._tracks_model.set_tracks(self._library.favorites())
        elif pid == HISTORY_ID:
            self._tracks_model.set_tracks(self._library.history())
        elif pid == "__local__":
            self._tracks_model.set_tracks(self._library.local_tracks())
        else:
            pl = self._library.get_playlist(pid)
            self._tracks_model.set_tracks(pl.songs if pl else [])
        self.tracksChanged.emit()

    def refresh_all(self) -> None:
        self._favorites_model.set_tracks(self._library.favorites())
        self._history_model.set_tracks(self._library.history())
        self._local_model.set_tracks(self._library.local_tracks())
        self._reload_tracks()
        self.favoritesChanged.emit()
        self.historyChanged.emit()
        self.localChanged.emit()
        self.playlistsChanged.emit()

    def _on_library_event(self, what: str) -> None:
        if what == "favorites":
            self._favorites_model.set_tracks(self._library.favorites())
            self.favoritesChanged.emit()
        elif what == "history":
            self._history_model.set_tracks(self._library.history())
            self.historyChanged.emit()
        elif what == "local":
            self._local_model.set_tracks(self._library.local_tracks())
            self.localChanged.emit()
        if self._selected_id and what in ("playlists", "favorites", "history", "local"):
            self._reload_tracks()
        self.playlistsChanged.emit()

    # ── 歌单 CRUD ───────────────────────────────────────────

    @Slot(str, result="QVariant")
    def createPlaylist(self, name: str):  # noqa: N802
        name = (name or "").strip()
        if not name:
            self.errorOccurred.emit("歌单名不能为空")
            return None
        pl = self._library.create_playlist(name)
        self._library.save()
        self.playlistsChanged.emit()
        self.message.emit(f"已创建歌单「{pl.name}」")
        return {"id": pl.id, "name": pl.name, "count": 0}

    @Slot(str, str, result=bool)
    def renamePlaylist(self, playlist_id: str, new_name: str) -> bool:  # noqa: N802
        ok = self._library.rename_playlist(playlist_id, new_name)
        if ok:
            self._library.save()
            self.playlistsChanged.emit()
            if self._selected_id == playlist_id:
                self.selectionChanged.emit()
            self.message.emit("歌单已重命名")
        else:
            self.errorOccurred.emit("系统歌单不可重命名")
        return ok

    @Slot(str, result=bool)
    def deletePlaylist(self, playlist_id: str) -> bool:  # noqa: N802
        ok = self._library.delete_playlist(playlist_id)
        if ok:
            self._library.save()
            if self._selected_id == playlist_id:
                self.select("")
            self.playlistsChanged.emit()
            self.message.emit("歌单已删除")
        else:
            self.errorOccurred.emit("系统歌单不可删除")
        return ok

    @Slot(str, "QVariant", result=bool)
    def addToPlaylist(self, playlist_id: str, value) -> bool:  # noqa: N802
        track = value if isinstance(value, Track) else Track.from_dict(value)
        if not track or not track.name:
            return False
        added = self._library.add_to_playlist(playlist_id, track)
        self._library.save()
        self.playlistsChanged.emit()
        if not added:
            self.message.emit("该歌曲已在歌单中")
        else:
            self.message.emit("已添加到歌单")
        return added

    @Slot(str, "QVariant", result=bool)
    def removeTrack(self, playlist_id: str, value) -> bool:  # noqa: N802
        track = value if isinstance(value, Track) else Track.from_dict(value)
        if not track:
            return False
        ok = self._library.remove_from_playlist(playlist_id, track.uid)
        if ok:
            self._library.save()
            self.playlistsChanged.emit()
            self.message.emit("已从歌单移除")
        return ok

    @Slot(str, int, int, result=bool)
    def moveTrack(self, playlist_id: str, src: int, dst: int) -> bool:  # noqa: N802
        ok = self._library.move_in_playlist(playlist_id, int(src), int(dst))
        if ok:
            self._library.save()
        return ok

    @Slot("QVariant", result=bool)
    def toggleFavorite(self, value) -> bool:  # noqa: N802
        track = value if isinstance(value, Track) else Track.from_dict(value)
        if not track or not track.name:
            return False
        state = self._library.toggle_favorite(track)
        self._library.save()
        self._favorites_model.set_tracks(self._library.favorites())
        self.favoritesChanged.emit()
        self.playlistsChanged.emit()
        self.message.emit("已加入我喜欢的音乐" if state else "已取消喜欢")
        return state

    @Slot("QVariant", result=int)
    def addManyToFavorites(self, items) -> int:  # noqa: N802
        """批量加入「我喜欢」，返回实际新增数量。"""
        added = 0
        for value in items or []:
            track = value if isinstance(value, Track) else Track.from_dict(value)
            if not track or not track.name:
                continue
            if not self._library.is_favorite(track):
                self._library.toggle_favorite(track)
                added += 1
        if added:
            self._library.save()
            self._favorites_model.set_tracks(self._library.favorites())
            self.favoritesChanged.emit()
            self.playlistsChanged.emit()
            self.message.emit(f"已添加 {added} 首到我喜欢的音乐")
        else:
            self.message.emit("这些歌曲都已经在「我喜欢」里了")
        return added

    @Slot("QVariant", result=bool)
    def isFavorite(self, value) -> bool:  # noqa: N802
        track = value if isinstance(value, Track) else Track.from_dict(value)
        return bool(track and self._library.is_favorite(track))

    @Slot("QVariant", result="QVariantList")
    def playlistsContaining(self, value):  # noqa: N802
        track = value if isinstance(value, Track) else Track.from_dict(value)
        if not track:
            return []
        return self._library.playlists_containing(track)

    @Slot(str, result=int)
    def get_playlist_count(self, playlist_id: str) -> int:  # noqa: N802
        pl = self._library.get_playlist(playlist_id)
        return pl.count if pl else 0

    @Slot(str, result=bool)
    def clearPlaylist(self, playlist_id: str) -> bool:  # noqa: N802
        ok = self._library.clear_playlist(playlist_id)
        if ok:
            self._library.save()
            self._reload_tracks()
            self.playlistsChanged.emit()
            self.message.emit("歌单已清空")
        else:
            self.errorOccurred.emit("系统歌单不可清空")
        return ok

    @Slot(str, str, result=bool)
    def setSortMode(self, playlist_id: str, mode: str) -> bool:  # noqa: N802
        ok = self._library.set_sort_mode(playlist_id, mode)
        if ok:
            self._library.save()
            self._reload_tracks()
        return ok

    @Slot(result=bool)
    def clearHistory(self) -> bool:  # noqa: N802
        self._library.clear_history()
        self._library.save()
        self._history_model.clear()
        self.historyChanged.emit()
        self.playlistsChanged.emit()
        self.message.emit("播放历史已清空")
        return True

    # ── 本地音乐 ────────────────────────────────────────────

    @Slot(str)
    def addLocalFolder(self, folder: str) -> None:
        folder = (folder or "").strip().strip('"')
        if not folder or not os.path.isdir(folder):
            self.errorOccurred.emit("请选择有效的文件夹")
            return
        folders = list(self._config.get("local.folders", []) or [])
        if folder in folders:
            self.message.emit("该文件夹已添加")
            return
        folders.append(folder)
        self._config.set("local.folders", folders)
        self.localChanged.emit()
        self.scan()

    @Slot(str)
    def removeLocalFolder(self, folder: str) -> None:
        folders = [f for f in (self._config.get("local.folders", []) or []) if f != folder]
        self._config.set("local.folders", folders)
        remaining = [t for t in self._library.local_tracks() if not t.path.startswith(folder)]
        self._library.set_local_tracks(remaining)
        self._library.save()
        self.localChanged.emit()
        self._on_library_event("local")

    @Slot()
    def scan(self) -> None:
        if self._scanning:
            return
        folders = list(self._config.get("local.folders", []) or [])
        if not folders:
            self.errorOccurred.emit("请先添加要扫描的文件夹")
            return
        self._scanning = True
        self._scan_total = 0
        self._scan_done = 0
        self.scanningChanged.emit()
        exts = self._config.get("local.extensions", None)
        threading.Thread(
            target=self._scan_worker, args=(folders, exts), daemon=True, name="scan-local"
        ).start()

    def _scan_worker(self, folders: List[str], exts) -> None:
        try:
            files: List[str] = []
            for folder in folders:
                files.extend(scan_local_folder(folder, exts or AUDIO_EXTENSIONS))
            # 去重
            seen = set()
            unique = []
            for f in files:
                key = os.path.normcase(os.path.abspath(f))
                if key not in seen:
                    seen.add(key)
                    unique.append(f)
            unique.sort(key=lambda p: name_sort_key(os.path.basename(p)))

            tracks: List[Track] = []
            for i, path in enumerate(unique):
                track = resolve_local_metadata(path)
                if track is not None:
                    tracks.append(track)
                self._emitter.scanProgress.emit((i + 1, len(unique)))
            self._emitter.scanDone.emit(tracks)
        except Exception as e:
            logger.exception("扫描本地音乐失败")
            self._emitter.scanDone.emit(e)

    @Slot(object)
    def _on_scan_progress(self, payload) -> None:
        try:
            done, total = payload
            self._scan_done = int(done)
            self._scan_total = int(total)
            self.scanningChanged.emit()
        except Exception:
            pass

    @Slot(object)
    def _on_scan_done(self, payload) -> None:
        self._scanning = False
        self.scanningChanged.emit()
        if isinstance(payload, Exception):
            self.errorOccurred.emit(f"扫描失败：{payload}")
            return
        tracks = list(payload or [])
        self._library.set_local_tracks(tracks)
        self._library.save()
        self.localChanged.emit()
        self._on_library_event("local")
        self.message.emit(f"扫描完成，共 {len(tracks)} 首本地歌曲")
