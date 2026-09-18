"""网易云补充接口（发现页 / 歌词翻译）。

FMCL 只用到搜索、播放地址、歌词、歌单与登录；这里在不改动 vendored ``wy.py``
的前提下，复用它的 eapi 加密通道补齐「发现页」需要的接口。

**通道选择**：全部走 eapi。实测本机环境下 ``music.163.com/weapi/*`` 会被风控
拦截返回空响应（与 ``wy.py:1345-1346`` 的注释一致），而
``interface3.music.163.com/eapi/api/*`` 正常返回。

所有接口都是**尽力而为**：失败时返回空结果，由 UI 优雅降级。
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from .base import MusicInfo

logger = logging.getLogger(__name__)

def _wy():
    from . import wy_source

    return wy_source()

def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        logger.debug("网易云补充接口失败: %s", e)
        return default

# ──────────────────────────────────────────────────────────────
# 歌词翻译 / 罗马音
# ──────────────────────────────────────────────────────────────

def fetch_translation(
    song_id: str, *, want_translation: bool = True, want_roma: bool = False
) -> Tuple[str, str]:
    """获取翻译歌词与罗马音歌词。

    FMCL 的 ``get_lyric`` 其实请求了 ``tv``/``rv`` 却只读 ``lrc.lyric``，
    翻译与罗马音形同虚设；这里真正接上。
    """
    if not song_id or not (want_translation or want_roma):
        return "", ""
    src = _wy()
    if src is None:
        return "", ""
    try:
        resp = src._eapi_post(  # noqa: SLF001 - 复用已实现的加密通道
            "/api/song/lyric",
            {"id": str(song_id), "lv": -1, "tv": -1, "rv": -1, "kv": -1},
        )
    except Exception as e:
        logger.debug("获取翻译歌词失败: %s", e)
        return "", ""
    if not isinstance(resp, dict):
        return "", ""

    def _pick(key: str) -> str:
        node = resp.get(key)
        if isinstance(node, dict):
            return str(node.get("lyric") or "")
        return ""

    translation = _pick("tlyric") if want_translation else ""
    roma = _pick("romalrc") if want_roma else ""
    return translation, roma

# ──────────────────────────────────────────────────────────────
# 发现页
# ──────────────────────────────────────────────────────────────

def recommend_playlists(limit: int = 30) -> List[Dict]:
    """推荐歌单。"""
    src = _wy()
    if src is None:
        return []
    resp = _safe(
        lambda: src._eapi_post(  # noqa: SLF001
            "/api/personalized/playlist", {"limit": int(limit), "total": True, "n": 1000}
        ),
        {},
    ) or {}
    out: List[Dict] = []
    for item in resp.get("result") or []:
        try:
            out.append(
                {
                    "id": str(item.get("id")),
                    "name": str(item.get("name") or ""),
                    "cover": str(item.get("picUrl") or ""),
                    "play_count": int(item.get("playCount") or 0),
                    "track_count": int(item.get("trackCount") or 0),
                    "description": str(item.get("copywriter") or ""),
                    "source": "wy",
                }
            )
        except Exception:
            continue
    return out

def new_songs(limit: int = 12) -> List[MusicInfo]:
    """最新音乐。"""
    src = _wy()
    if src is None:
        return []
    resp = _safe(
        lambda: src._eapi_post("/api/personalized/newsong", {"limit": int(limit)}),  # noqa: SLF001
        {},
    ) or {}
    songs = []
    for item in resp.get("result") or []:
        song = item.get("song") if isinstance(item, dict) else None
        if isinstance(song, dict):
            songs.append(song)
        elif isinstance(item, dict) and item.get("id"):
            songs.append(item)
    return _parse_songs(src, songs)

def toplists() -> List[Dict]:
    """官方排行榜（飙升榜 / 新歌榜 / 热歌榜 …）。"""
    src = _wy()
    if src is None:
        return []
    resp = _safe(
        lambda: src._eapi_post("/api/toplist/detail", {}),  # noqa: SLF001
        {},
    ) or {}
    out: List[Dict] = []
    for item in resp.get("list") or []:
        try:
            cover = str(item.get("coverImgUrl") or "")
            if not cover:
                cover = str((item.get("playlist") or {}).get("coverImgUrl") or "")
            out.append(
                {
                    "id": str(item.get("id") or (item.get("playlist") or {}).get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "cover": cover,
                    "update_frequency": str(item.get("updateFrequency") or ""),
                    "track_count": int(item.get("trackCount") or 0),
                    "source": "wy",
                }
            )
        except Exception:
            continue
    return [t for t in out if t["id"]]

def hot_searches() -> List[Dict]:
    """热搜榜（接口不可用时返回空）。"""
    src = _wy()
    if src is None:
        return []
    for path in ("/api/search/hot/detail", "/api/search/hot"):
        resp = _safe(lambda p=path: src._eapi_post(p, {}), None)  # noqa: SLF001
        if isinstance(resp, dict) and resp.get("code") == 200:
            data = resp.get("data") or resp.get("result") or {}
            items = data.get("hots") if isinstance(data, dict) else data
            out = []
            for item in items or []:
                try:
                    out.append(
                        {
                            "keyword": str(item.get("searchWord") or item.get("first") or ""),
                            "score": int(item.get("score") or item.get("second") or 0),
                        }
                    )
                except Exception:
                    continue
            if out:
                return out[:20]
    return []

def daily_recommend() -> List[MusicInfo]:
    """每日推荐歌曲（需登录）。"""
    src = _wy()
    if src is None or not _safe(lambda: src.is_logged_in(), False):
        return []
    resp = _safe(
        lambda: src._eapi_post("/api/v1/discovery/recommend/songs", {"limit": 100}),  # noqa: SLF001
        {},
    ) or {}
    songs = ((resp.get("data") or {}).get("dailySongs")) or (resp.get("recommend") or [])
    return _parse_songs(src, songs)

def playlist_tracks(playlist_id: str) -> List[MusicInfo]:
    """歌单歌曲（复用音源已有的多路由实现）。"""
    src = _wy()
    if src is None:
        return []
    return _safe(lambda: src.get_playlist_tracks(str(playlist_id)), []) or []

def playlist_meta(playlist_id: str) -> Dict:
    """歌单基本信息（名称 / 封面 / 简介 / 作者）。"""
    src = _wy()
    if src is None:
        return {}
    resp = _safe(
        lambda: src._eapi_post(  # noqa: SLF001
            "/api/v6/playlist/detail", {"id": str(playlist_id), "n": 1, "s": 0}
        ),
        {},
    ) or {}
    pl = resp.get("playlist") or {}
    if not pl:
        return {}
    return {
        "id": str(pl.get("id") or playlist_id),
        "name": str(pl.get("name") or ""),
        "cover": str(pl.get("coverImgUrl") or ""),
        "description": str(pl.get("description") or ""),
        "track_count": int(pl.get("trackCount") or 0),
        "play_count": int(pl.get("playCount") or 0),
        "creator": str((pl.get("creator") or {}).get("nickname") or ""),
    }

def _parse_songs(src, songs) -> List[MusicInfo]:
    """把网易云歌曲 JSON 转成 ``MusicInfo``（优先复用音源自身的解析器）。"""
    if not songs:
        return []
    try:
        parser = getattr(src, "_parse_song_detail_songs", None)
        if parser is not None:
            parsed = parser(songs)
            if parsed:
                return parsed
    except Exception as e:
        logger.debug("复用网易云解析器失败，改用内置解析: %s", e)

    out: List[MusicInfo] = []
    for item in songs:
        try:
            artists = item.get("ar") or item.get("artists") or []
            album = item.get("al") or item.get("album") or {}
            out.append(
                MusicInfo(
                    name=str(item.get("name") or ""),
                    singer="、".join(str(a.get("name") or "") for a in artists),
                    source="wy",
                    songmid=str(item.get("id") or ""),
                    album_name=str(album.get("name") or ""),
                    album_id=str(album.get("id") or ""),
                    interval=int((item.get("dt") or item.get("duration") or 0) / 1000),
                    img=str(album.get("picUrl") or ""),
                    fee=int((item.get("privilege") or {}).get("fee") or item.get("fee") or 0),
                )
            )
        except Exception:
            continue
    return out
