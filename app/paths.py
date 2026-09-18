"""程序路径解析。

所有运行时数据（配置、凭据、缓存、歌单）默认落在**程序所在目录**下，
使整个应用保持绿色/便携：拷贝目录即可带走全部数据。

可通过环境变量 `FUSION_MUSIC_HOME` 或命令行 `--data-dir` 覆盖。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

APP_NAME = "FusionMusicPlayer"
APP_DISPLAY_NAME = "Fusion Music Player"
ORG_NAME = "FusionLab"

# 版本号的唯一来源是 app/_version.py（由 scripts/release.py 更新，
# 发布流水线在打包前会依据 git tag 覆写一次）。
# 保留兜底是为了在文件被误删时仍能启动，而不是隐藏错误。
try:  # pragma: no cover
    from ._version import APP_VERSION
except ImportError:  # pragma: no cover
    APP_VERSION = "0.0.0-unknown"

_DATA_DIR_OVERRIDE: Optional[Path] = None


def program_dir() -> Path:
    """程序所在目录（打包后为 exe 目录，开发时为项目根目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _writable(path: Path) -> bool:
    """探测目录是否可写（安装到 Program Files 时需要回退）。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / f".write_probe_{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _fallback_dir() -> Path:
    """程序目录不可写时的回退位置。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / APP_NAME


def set_data_dir(path: str | os.PathLike | None) -> None:
    """覆盖数据根目录（由命令行参数或环境变量调用）。"""
    global _DATA_DIR_OVERRIDE
    _DATA_DIR_OVERRIDE = Path(path).expanduser().resolve() if path else None


def data_dir() -> Path:
    """数据根目录：默认为『程序当前目录』。

    程序目录不可写时（例如解压到 ``Program Files``）自动回退到用户目录，
    避免便携版在被安装后无法保存设置与歌单。
    """
    if _DATA_DIR_OVERRIDE is not None:
        return _DATA_DIR_OVERRIDE
    env = os.environ.get("FUSION_MUSIC_HOME")
    if env:
        return Path(env).expanduser().resolve()
    target = program_dir() / "data"
    if _writable(target):
        return target
    return _fallback_dir()


def cache_dir() -> Path:
    return data_dir() / "cache"


def cover_cache_dir() -> Path:
    return cache_dir() / "cover"


def lyric_cache_dir() -> Path:
    return cache_dir() / "lyric"


def media_cache_dir() -> Path:
    return cache_dir() / "media"


def config_file() -> Path:
    return data_dir() / "config.json"


def credentials_file() -> Path:
    """加密凭据文件（网易云登录态等）。"""
    return data_dir() / "credentials.enc"


def key_file() -> Path:
    """主密钥文件（Windows 下由 DPAPI 包裹）。"""
    return data_dir() / "keys" / "master.key"


def playlists_file() -> Path:
    return data_dir() / "playlists.json"


def history_file() -> Path:
    return data_dir() / "history.json"


def favorites_file() -> Path:
    return data_dir() / "favorites.json"


def log_dir() -> Path:
    return data_dir() / "logs"


def qml_dir() -> Path:
    return Path(__file__).resolve().parent / "ui"


def resource(path: str) -> str:
    """返回 QML 可用的本地文件 URL 字符串。"""
    from PySide6.QtCore import QUrl

    p = Path(path)
    if not p.is_absolute():
        p = qml_dir() / path
    return QUrl.fromLocalFile(str(p)).toString()


def ensure_dirs() -> None:
    for d in (
        data_dir(),
        cache_dir(),
        cover_cache_dir(),
        lyric_cache_dir(),
        media_cache_dir(),
        log_dir(),
        key_file().parent,
    ):
        d.mkdir(parents=True, exist_ok=True)
