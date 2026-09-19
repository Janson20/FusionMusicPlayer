"""设置控制器：读写配置、缓存管理、程序目录信息。"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import List

from PySide6.QtCore import QObject, Property, Signal, Slot

from .. import paths
from ..config import DEFAULTS
from ..core import cache

logger = logging.getLogger(__name__)

QUALITY_OPTIONS = [
    {"id": "auto", "name": "自动（按可用最高音质）"},
    {"id": "flac24bit", "name": "Hi-Res 母带"},
    {"id": "flac", "name": "无损 FLAC"},
    {"id": "320k", "name": "高品质 320K"},
    {"id": "128k", "name": "标准 128K"},
]

THEME_OPTIONS = [
    {"id": "auto", "name": "跟随系统"},
    {"id": "light", "name": "浅色"},
    {"id": "dark", "name": "深色"},
]

ACCENT_PRESETS = [
    {"id": "#6C4DF6", "name": "星云紫"},
    {"id": "#3B82F6", "name": "冰川蓝"},
    {"id": "#0EA5A4", "name": "青竹"},
    {"id": "#E5484D", "name": "朱砂"},
    {"id": "#F59E0B", "name": "琥珀"},
    {"id": "#EC4899", "name": "绯樱"},
]

LYRIC_ALIGN_OPTIONS = [
    {"id": "left", "name": "靠左"},
    {"id": "center", "name": "居中"},
    {"id": "right", "name": "靠右"},
]

# 歌词对齐的合法取值，非法值一律回落到居中
LYRIC_ALIGNMENTS = ("left", "center", "right")

class SettingsController(QObject):
    changed = Signal()
    cacheChanged = Signal()
    message = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config

    # ── 只读信息 ────────────────────────────────────────────

    @Property(str, constant=True)
    def dataDir(self) -> str:  # noqa: N802
        return str(paths.data_dir())

    @Property(str, constant=True)
    def programDir(self) -> str:  # noqa: N802
        return str(paths.program_dir())

    @Property(str, constant=True)
    def credentialPath(self) -> str:  # noqa: N802
        return str(paths.credentials_file())

    @Property(str, constant=True)
    def cacheDir(self) -> str:  # noqa: N802
        return str(paths.cache_dir())

    @Property(str, constant=True)
    def downloadDir(self) -> str:  # noqa: N802
        configured = str(self._config.get("storage.download_dir", "") or "")
        return configured or str(paths.program_dir() / "downloads")

    @Property("QVariantList", constant=True)
    def qualityOptions(self):  # noqa: N802
        return QUALITY_OPTIONS

    @Property("QVariantList", constant=True)
    def themeOptions(self):  # noqa: N802
        return THEME_OPTIONS

    @Property("QVariantList", constant=True)
    def accentPresets(self):  # noqa: N802
        return ACCENT_PRESETS

    # ── 可写设置 ────────────────────────────────────────────

    @Property(str, notify=changed)
    def theme(self) -> str:
        return str(self._config.get("appearance.theme", "auto"))

    @Property(str, notify=changed)
    def accent(self) -> str:
        return str(self._config.get("appearance.accent", "#6C4DF6"))

    @Property(bool, notify=changed)
    def animations(self) -> bool:
        return bool(self._config.get("appearance.animations", True))

    @Property(bool, notify=changed)
    def navExpanded(self) -> bool:  # noqa: N802
        return bool(self._config.get("appearance.nav_expanded", True))

    @Property(str, notify=changed)
    def quality(self) -> str:
        return str(self._config.get("playback.quality", "320k"))

    @Property(bool, notify=changed)
    def fallback(self) -> bool:
        return bool(self._config.get("sources.fallback", True))

    @Property(bool, notify=changed)
    def preferOriginal(self) -> bool:  # noqa: N802
        return bool(self._config.get("sources.prefer_original", True))

    @Property(bool, notify=changed)
    def cacheCover(self) -> bool:  # noqa: N802
        return bool(self._config.get("storage.cache_cover", True))

    @Property(bool, notify=changed)
    def cacheLyric(self) -> bool:  # noqa: N802
        return bool(self._config.get("storage.cache_lyric", True))

    @Property(bool, notify=changed)
    def cacheMedia(self) -> bool:  # noqa: N802
        return bool(self._config.get("storage.cache_media", False))

    @Property(int, notify=changed)
    def mediaCacheLimit(self) -> int:  # noqa: N802
        return int(self._config.get("storage.media_cache_limit_mb", 2048) or 2048)

    @Property(bool, notify=changed)
    def showTranslation(self) -> bool:  # noqa: N802
        return bool(self._config.get("lyrics.show_translation", True))

    @Property(bool, notify=changed)
    def showRomaji(self) -> bool:  # noqa: N802
        return bool(self._config.get("lyrics.show_romaji", False))

    @Property(int, notify=changed)
    def lyricFontSize(self) -> int:  # noqa: N802
        return int(self._config.get("lyrics.font_size", 17) or 17)

    @Property(str, notify=changed)
    def lyricAlignment(self) -> str:  # noqa: N802
        value = str(self._config.get("lyrics.alignment", "center") or "").strip().lower()
        return value if value in LYRIC_ALIGNMENTS else "center"

    @Property("QVariantList", constant=True)
    def lyricAlignOptions(self):  # noqa: N802
        return LYRIC_ALIGN_OPTIONS

    @Property(bool, notify=changed)
    def desktopLyric(self) -> bool:  # noqa: N802
        return bool(self._config.get("lyrics.desktop_lyric", False))

    @Property(bool, notify=changed)
    def autoLogin(self) -> bool:  # noqa: N802
        return bool(self._config.get("account.auto_login", True))

    @Property(bool, notify=changed)
    def saveCredentials(self) -> bool:  # noqa: N802
        return bool(self._config.get("account.save_credentials", True))

    @Property(int, notify=changed)
    def cookieRefreshDays(self) -> int:  # noqa: N802
        """凭据剩余有效期少于这么多天时自动续期（0 = 关闭）。"""
        try:
            return int(self._config.get("account.cookie_refresh_days", 7) or 0)
        except (TypeError, ValueError):
            return 7

    @Property(bool, notify=changed)
    def scanOnStart(self) -> bool:  # noqa: N802
        return bool(self._config.get("local.scan_on_start", False))

    @Property("QVariantList", notify=changed)
    def enabledSources(self):  # noqa: N802
        from ..sources import SOURCE_META

        enabled = set(self._config.get("sources.enabled", []) or [])
        return [
            {"id": m["id"], "name": m["name"], "enabled": m["id"] in enabled}
            for m in SOURCE_META
        ]

    @Property("QVariant", notify=changed)
    def allSettings(self):  # noqa: N802
        return self._config.as_dict()

    # ── 写入 ────────────────────────────────────────────────

    @Slot(str, "QVariant")
    def set(self, key: str, value) -> None:  # noqa: A003
        self._config.set(str(key), value)
        self.changed.emit()

    @Slot(str, bool)
    def setBool(self, key: str, value: bool) -> None:  # noqa: N802
        self._config.set(str(key), bool(value))
        self.changed.emit()

    @Slot(str, int)
    def setInt(self, key: str, value: int) -> None:  # noqa: N802
        self._config.set(str(key), int(value))
        self.changed.emit()

    @Slot(str, str, bool)
    def setSourceEnabled(self, source_id: str, enabled: bool) -> None:  # noqa: N802
        enabled_list: List[str] = list(self._config.get("sources.enabled", []) or [])
        if enabled and source_id not in enabled_list:
            enabled_list.append(source_id)
        elif not enabled and source_id in enabled_list:
            enabled_list.remove(source_id)
        if not enabled_list:
            self.errorOccurred.emit("至少需要启用一个音源")
            return
        self._config.set("sources.enabled", enabled_list)
        self.changed.emit()
        self.message.emit("音源设置已更新")

    @Slot(str, result=bool)
    def moveSourceUp(self, source_id: str) -> bool:  # noqa: N802
        order: List[str] = list(self._config.get("sources.priority", []) or [])
        if source_id not in order or order.index(source_id) == 0:
            return False
        i = order.index(source_id)
        order[i - 1], order[i] = order[i], order[i - 1]
        self._config.set("sources.priority", order)
        self.changed.emit()
        return True

    # ── 缓存 ────────────────────────────────────────────────

    @Property("QVariant", notify=cacheChanged)
    def cacheStats(self):  # noqa: N802
        try:
            raw = cache.cache_stats()
        except Exception:
            raw = {"cover": 0, "lyric": 0, "media": 0}
        total = sum(raw.values())
        return {
            "cover": _human(raw.get("cover", 0)),
            "lyric": _human(raw.get("lyric", 0)),
            "media": _human(raw.get("media", 0)),
            "total": _human(total),
            "totalBytes": total,
        }

    @Slot()
    def refreshCache(self) -> None:  # noqa: N802
        self.cacheChanged.emit()

    @Slot()
    def clearCache(self) -> None:  # noqa: N802
        try:
            cache.clear_cache()
            self.message.emit("缓存已清空")
        except Exception as e:
            logger.warning("清空缓存失败: %s", e)
            self.errorOccurred.emit("清空缓存失败")
        self.cacheChanged.emit()

    @Slot(str)
    def clearCachePart(self, part: str) -> None:  # noqa: N802
        try:
            cache.clear_cache(str(part))
            self.message.emit("已清理缓存")
        except Exception as e:
            logger.warning("清理缓存失败: %s", e)
        self.cacheChanged.emit()

    @Slot()
    def trimCache(self) -> None:  # noqa: N802
        cache.trim_cache(self.mediaCacheLimit)
        self.refreshCache()
        self.message.emit("已按配额清理缓存")

    # ── 系统操作 ────────────────────────────────────────────

    @Slot(str)
    def openPath(self, path: str) -> None:  # noqa: N802
        target = path or str(paths.data_dir())
        try:
            if sys.platform == "win32":
                os.startfile(target)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target])
            else:
                subprocess.Popen(["xdg-open", target])
        except Exception as e:
            logger.warning("打开路径失败: %s", e)
            self.errorOccurred.emit(f"无法打开路径：{target}")

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:  # noqa: N802
        try:
            from PySide6.QtGui import QGuiApplication

            QGuiApplication.clipboard().setText(str(text or ""))
            self.message.emit("已复制到剪贴板")
        except Exception as e:
            logger.debug("复制失败: %s", e)

    @Slot()
    def resetAll(self) -> None:
        self._config.reset()
        self.changed.emit()
        self.message.emit("设置已恢复默认值")

    @Slot(result="QVariant")
    def defaults(self):  # noqa: N802
        return DEFAULTS

def _human(size: int) -> str:
    try:
        s = float(size)
    except (TypeError, ValueError):
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if s < 1024 or unit == "GB":
            return f"{s:.0f} {unit}" if unit == "B" else f"{s:.1f} {unit}"
        s /= 1024
    return f"{s:.1f} GB"
