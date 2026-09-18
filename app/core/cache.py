"""封面 / 歌词 / 音频文件缓存。

全部落在程序目录 ``data/cache/`` 下，键为 URL 的 SHA-1 前 16 位，
附带最小可用的磁盘配额清理。
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Dict, Optional

import requests

from .. import paths

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_session_lock = threading.Lock()
_session: Optional[requests.Session] = None

def session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            s = requests.Session()
            s.headers.update({"User-Agent": DEFAULT_UA})
            _session = s
        return _session

def key_for(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]

def _download(url: str, dest: Path, headers: Optional[Dict[str, str]] = None,
              cookies: Optional[Dict[str, str]] = None, timeout: int = 30) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".part")
        os.close(fd)
        tmp_path = Path(tmp)
        with session().get(
            url, headers=headers or {}, cookies=cookies or {}, timeout=timeout, stream=True
        ) as resp:
            resp.raise_for_status()
            size = 0
            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(65536):
                    if chunk:
                        f.write(chunk)
                        size += len(chunk)
        if size <= 0:
            tmp_path.unlink(missing_ok=True)
            return False
        os.replace(tmp_path, dest)
        return True
    except Exception as e:
        logger.debug("下载失败 %s: %s", url, e)
        try:
            Path(tmp).unlink(missing_ok=True)  # type: ignore[possibly-undefined]
        except Exception:
            pass
        return False

def fetch_cached(
    url: str,
    subdir: str,
    suffix: str = "",
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """下载并缓存到 ``data/cache/<subdir>/``，返回本地路径。"""
    if not url:
        return None
    if url.startswith("file://"):
        return url
    if not suffix:
        suffix = Path(url.split("?")[0]).suffix or ".bin"
    base = {
        "cover": paths.cover_cache_dir,
        "lyric": paths.lyric_cache_dir,
        "media": paths.media_cache_dir,
    }.get(subdir)
    if base is None:
        base = paths.cache_dir() / subdir
    dest = base() / f"{key_for(url)}{suffix}"
    if dest.exists() and dest.stat().st_size > 0:
        return str(dest)
    if _download(url, dest, headers, cookies):
        return str(dest)
    return None

def cached_cover(url: str) -> Optional[str]:
    """封面缓存；返回 ``file://`` URL 供 QML Image 直接使用。"""
    p = fetch_cached(url, "cover")
    if not p:
        return None
    from PySide6.QtCore import QUrl

    return QUrl.fromLocalFile(p).toString()

def cached_lyric(url: str) -> Optional[str]:
    return fetch_cached(url, "lyric", suffix=".lrc")

def cached_media(url: str, suffix: str = "", headers=None, cookies=None) -> Optional[str]:
    return fetch_cached(url, "media", suffix=suffix, headers=headers, cookies=cookies)

# ──────────────────────────────────────────────────────────────
# 配额清理
# ──────────────────────────────────────────────────────────────

def directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except OSError:
            pass
    return total

def trim_cache(limit_mb: int, subdir: str = "media") -> int:
    """按 LRU 淘汰，返回删除的文件数。"""
    base = {
        "cover": paths.cover_cache_dir,
        "lyric": paths.lyric_cache_dir,
        "media": paths.media_cache_dir,
    }.get(subdir, lambda: paths.cache_dir() / subdir)()
    if not base.exists():
        return 0
    limit = max(0, int(limit_mb)) * 1024 * 1024
    files = []
    for p in base.rglob("*"):
        try:
            if p.is_file():
                st = p.stat()
                files.append((st.st_atime, st.st_size, p))
        except OSError:
            pass
    total = sum(f[1] for f in files)
    if total <= limit:
        return 0
    files.sort(key=lambda x: x[0])
    removed = 0
    for _atime, size, p in files:
        if total <= limit:
            break
        try:
            p.unlink()
            total -= size
            removed += 1
        except OSError:
            pass
    if removed:
        logger.info("已清理 %s 缓存 %d 个文件", subdir, removed)
    return removed

def clear_cache(subdir: Optional[str] = None) -> None:
    base = paths.cache_dir() if subdir is None else paths.cache_dir() / subdir
    if base.exists():
        shutil.rmtree(base, ignore_errors=True)
    paths.ensure_dirs()

def cache_stats() -> Dict[str, int]:
    return {
        "cover": directory_size(paths.cover_cache_dir()),
        "lyric": directory_size(paths.lyric_cache_dir()),
        "media": directory_size(paths.media_cache_dir()),
    }

def touch(path: str) -> None:
    """刷新访问时间，避免刚用过的缓存被 LRU 淘汰。"""
    try:
        os.utime(path, None)
    except OSError:
        pass
