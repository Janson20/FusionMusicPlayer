"""把曲目解析为「可播放的 URL 或本地文件」。

沿用 FMCL 的判定链，但适配流式播放：

1. 本地文件 → 校验存在与文件头
2. 在线曲目 → ``sources.get_music_url()``（内部已含同源音质降级）
3. 该音源需要额外请求头 / Cookie（如 B 站 Referer）→ 先下载到缓存再播
4. 仍失败 → ``sources.resolve_track()`` 跨源兜底（换平台找同曲）
5. 下载得到的文件再做**文件头 + 时长**双重校验，防止把 HTML 错误页或
   VIP 试听片段当成完整曲目（这两条校验直接取自 FMCL，是防坑的核心）
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from . import cache
from .models import LOCAL_SOURCE, Track
from .. import sources

logger = logging.getLogger(__name__)

# FMCL app_music.py:135-144
_AUDIO_FILE_MAGIC = ((b"ID3", ".mp3"), (b"fLaC", ".flac"), (b"OggS", ".ogg"), (b"RIFF", ".wav"))
_M4A_FTYP_MAGIC = b"ftyp"
_DURATION_TOLERANCE_RATIO = 0.2
_DURATION_TOLERANCE_MIN_SEC = 10

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus", ".aiff", ".ape", ".mp4", ".m4s"
}

@dataclass
class Resolved:
    """解析结果。"""

    track: Track           # 实际拿去播放的曲目（兜底后可能换了音源）
    target: str            # 本地路径或 http(s) URL
    is_local: bool         # target 是否为本地文件
    quality: str           # 实际使用的音质档位
    fallback: bool = False  # 是否发生了跨源兜底
    requested: Optional[Track] = None  # 用户最初点播的曲目（兜底时为原曲）

    @property
    def play_url(self) -> str:
        if self.is_local:
            from PySide6.QtCore import QUrl

            return QUrl.fromLocalFile(self.target).toString()
        return self.target

    @property
    def display_track(self) -> Track:
        return self.requested or self.track

# ──────────────────────────────────────────────────────────────
# 校验（逐字沿用 FMCL 的判据）
# ──────────────────────────────────────────────────────────────

def validate_audio_file_header(filepath: str) -> bool:
    """校验音频文件头，拦截 HTML 错误页 / 空文件。"""
    try:
        if not os.path.exists(filepath):
            return False
        if os.path.getsize(filepath) == 0:
            return False
        with open(filepath, "rb") as f:
            head = f.read(16)
        if not head:
            return False
        for magic, _ext in _AUDIO_FILE_MAGIC:
            if head.startswith(magic):
                return True
        if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
            return True
        if len(head) >= 8 and head[4:8] == _M4A_FTYP_MAGIC:
            return True
        return False
    except OSError:
        return False

def validate_audio_duration(filepath: str, expected_seconds: int) -> bool:
    """校验实际时长与期望时长的偏差，拦截 VIP 试听片段。

    任一时长未知（<=0）时放行，避免误杀。
    """
    if expected_seconds <= 0:
        return True
    actual = probe_duration(filepath)
    if actual <= 0:
        return True
    tolerance = max(_DURATION_TOLERANCE_MIN_SEC, int(expected_seconds * _DURATION_TOLERANCE_RATIO))
    return abs(actual - expected_seconds) <= tolerance

def probe_duration(filepath: str) -> int:
    """用 mutagen 读取时长（秒），失败返回 0。"""
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(filepath)
        if mf is not None and getattr(mf, "info", None) is not None:
            return int(getattr(mf.info, "length", 0) or 0)
    except Exception:
        pass
    return 0

# ──────────────────────────────────────────────────────────────
# 解析
# ──────────────────────────────────────────────────────────────

def resolve(
    track: Track,
    quality: str = "320k",
    *,
    allow_fallback: bool = True,
    exclude_sources: Optional[list] = None,
    cache_media: bool = False,
) -> Optional[Resolved]:
    """把曲目解析为可播放目标。"""
    if track is None:
        return None

    # ── 本地文件 ────────────────────────────────────────────
    if track.is_local or track.source == LOCAL_SOURCE:
        if not track.path or not os.path.exists(track.path):
            logger.warning("本地文件不存在: %s", track.path)
            return None
        return Resolved(
            track=track,
            target=track.path,
            is_local=True,
            quality=_local_quality(track.path),
            requested=track,
        )

    # ── 在线曲目 ────────────────────────────────────────────
    url = sources.get_music_url(track.to_music_info(), quality, track.source)
    if url:
        target = _maybe_localize(track, url, cache_media=cache_media)
        if target:
            return Resolved(
                track=track,
                target=target[0],
                is_local=target[1],
                quality=_effective_quality(track, quality),
                requested=track,
            )
        logger.info("音源 %s 返回的地址无法使用，转入跨源兜底: %s", track.source, track.name)
    else:
        logger.info("音源 %s 无可用地址: %s - %s", track.source, track.name, track.singer)

    # ── 跨源兜底 ────────────────────────────────────────────
    if allow_fallback and track.name:
        result = sources.resolve_track(
            track.to_music_info(), quality, excluded_sources=exclude_sources
        )
        if result:
            info, fb_url = result
            fb_track = Track.from_music_info(info)
            fb_track.path = ""
            target = _maybe_localize(fb_track, fb_url, cache_media=True)
            if target:
                return Resolved(
                    track=fb_track,
                    target=target[0],
                    is_local=target[1],
                    quality=_effective_quality(fb_track, quality),
                    fallback=True,
                    requested=track,
                )

    logger.warning("解析失败，所有音源均不可用: %s - %s", track.name, track.singer)
    return None

def _effective_quality(track: Track, requested: str) -> str:
    if requested == "auto":
        try:
            return track.best_quality
        except Exception:
            return "128k"
    return requested

def _local_quality(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".flac":
        return "flac"
    if ext == ".ape":
        return "flac"
    if ext in (".wav", ".aiff"):
        return "lossless"
    if ext in (".m4a", ".aac", ".opus"):
        return "320k"
    return "320k"

def _maybe_localize(
    track: Track, url: str, *, cache_media: bool
) -> Optional[Tuple[str, bool]]:
    """决定直接流式播放还是先下载到本地。

    返回 ``(目标, 是否本地文件)``；``None`` 表示该地址不可用。
    """
    if not url:
        return None
    headers = sources.download_headers(track.source)
    cookies = sources.download_cookies(track.source)

    # 需要自定义请求头 / Cookie 时 QMediaPlayer 无法直接带，改为先下载
    need_download = cache_media or bool(headers) or bool(cookies)

    if not need_download:
        # 无额外头要求的音源直接流式播放，起播快且支持拖动进度
        return (url, False)

    suffix = Path(url.split("?")[0]).suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        suffix = ".mp3"
    local = cache.cached_media(url, suffix=suffix, headers=headers, cookies=cookies)
    if not local:
        return None
    if not validate_audio_file_header(local):
        logger.warning("下载内容不是有效音频（可能是错误页）: %s", track.name)
        try:
            os.unlink(local)
        except OSError:
            pass
        return None
    if not validate_audio_duration(local, track.interval):
        logger.warning("下载内容时长异常（可能是试听片段）: %s", track.name)
        try:
            os.unlink(local)
        except OSError:
            pass
        return None
    cache.touch(local)
    return (local, True)

def resolve_local_metadata(path: str) -> Optional[Track]:
    """读取本地音频文件的标签，构造 :class:`Track`。"""
    p = Path(path)
    if not p.exists() or p.suffix.lower() not in AUDIO_EXTENSIONS:
        return None

    name = p.stem
    singer = ""
    album = ""
    duration = 0
    cover = ""
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(path, easy=True)
        if mf is not None:
            tags: Dict[str, object] = dict(mf.tags or {})
            name = _first(tags, ("title", "TIT2")) or name
            singer = _first(tags, ("artist", "TPE1")) or ""
            album = _first(tags, ("album", "TALB")) or ""
            if getattr(mf, "info", None) is not None:
                duration = int(getattr(mf.info, "length", 0) or 0)
    except Exception as e:
        logger.debug("读取标签失败 %s: %s", path, e)

    return Track(
        source=LOCAL_SOURCE,
        songmid=str(p.resolve()),
        name=name,
        singer=singer,
        album=album,
        interval=duration,
        cover=cover,
        path=str(p.resolve()),
    )

def _first(tags: Dict[str, object], keys) -> str:
    for k in keys:
        v = tags.get(k)
        if not v:
            continue
        if isinstance(v, (list, tuple)):
            if v:
                return str(v[0])
        else:
            return str(v)
    return ""

def scan_local_folder(folder: str, extensions=None) -> list:
    """递归扫描文件夹中的音频文件。"""
    exts = set(extensions or AUDIO_EXTENSIONS)
    root = Path(folder)
    if not root.exists():
        return []
    found = []
    for p in root.rglob("*"):
        try:
            if p.is_file() and p.suffix.lower() in exts:
                found.append(str(p))
        except OSError:
            continue
    found.sort()
    return found
