"""启动画面：对外只有"准备好底图 → 起画面 → 首帧时收掉"这三件事。

纯 Win32（ctypes + GDI）实现，**不依赖 Qt** —— 见 :mod:`app.splash_window`
（窗口与绘图）与 :mod:`app.splash_win32`（Win32 原型）。这个文件负责：

* 解析 ``tools/make_splash.py`` 生成的底图（``assets/splash-*.dat``）；
* 按 ``data/config.json`` 决定用深色还是浅色、进度条什么颜色；
* 对外提供 :func:`start`，并且**任何失败都只是"这次没有启动画面"**。

为什么必须"不用 Qt"
------------------
实测（``tools/probe_startup.py``）：**优化前**源码运行从进程创建到首帧可见约
2.1 秒，其中 requests 导入 ~0.4 秒、PySide6 ~0.15 秒、QML 编译 ~0.7 秒。
这段时间里**窗口根本不存在**，用户看到的就是"点了图标没反应"。
所以要在这之前画点东西出来，只能自己调系统 API。
"""

from __future__ import annotations

import os
import struct
import traceback
import zlib
from pathlib import Path
from typing import Optional

from .splash_window import WINDOWS as _WINDOWS
from .splash_window import Splash

__all__ = ["start", "Splash", "load_art", "read_prefs"]

MAGIC, VERSION, HEADER_SIZE = b"FMPS", 1, 104
DEFAULT_ACCENT = (0x6C, 0x4D, 0xF6)  # 与 app/config.py 的 appearance.accent 默认值一致


class Art:
    """一份解码好的底图（预乘 BGRA，逐行自上而下）。"""

    __slots__ = ("width", "height", "pixels", "art_size", "title_rect", "status_rect",
                 "bar_rect", "title_color", "status_color", "title_px", "status_px")

    def __init__(self, header: bytes, payload: bytes) -> None:
        magic, version, _flags = struct.unpack_from("<4sHH", header, 0)
        if magic != MAGIC:
            raise ValueError("不是启动画面资源")
        if version != VERSION:
            raise ValueError(f"启动画面资源版本不支持：{version}")
        width, height, art_w, art_h, stride, raw_len, zlen = struct.unpack_from("<7I", header, 8)
        layout = struct.unpack_from("<17I", header, 36)
        self.width, self.height = width, height
        self.art_size = (art_w, art_h)
        self.title_rect = layout[0:4]
        self.status_rect = layout[4:8]
        self.bar_rect = layout[8:12]
        self.title_color, self.status_color, self.title_px, self.status_px = layout[12:16]
        self.pixels = zlib.decompress(payload[:zlen])
        if len(self.pixels) != stride * art_h or len(self.pixels) != raw_len:
            raise ValueError("启动画面资源长度不符")


def load_art(path: Path) -> Optional[Art]:
    """读 ``splash-*.dat``；文件缺失或损坏都返回 None（当作"没有启动画面"）。"""
    try:
        data = path.read_bytes()
        if len(data) < HEADER_SIZE:
            return None
        return Art(data[:HEADER_SIZE], data[HEADER_SIZE:])
    except Exception:
        return None


def _system_prefers_dark() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return not winreg.QueryValueEx(key, "AppsUseLightTheme")[0]
    except OSError:
        return True


def read_prefs(data_dir: Optional[Path]) -> tuple[str, tuple[int, int, int]]:
    """按 ``data/config.json`` 决定底图与强调色；读不到就深色 + 默认紫。"""
    import json

    theme, accent = "auto", DEFAULT_ACCENT
    try:
        if data_dir is not None:
            raw = json.loads((Path(data_dir) / "config.json").read_text(encoding="utf-8"))
            # 节名是 appearance（见 app/config.py 的 DEFAULTS），不是 ui
            section = raw.get("appearance") or {}
            theme = str(section.get("theme") or "auto")
            value = str(section.get("accent") or "").lstrip("#")
            if len(value) == 6:
                accent = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except Exception:
        pass
    if theme not in ("light", "dark"):
        theme = "dark" if _system_prefers_dark() else "light"
    return theme, accent



def start(data_dir: Optional[Path] = None, assets_dir: Optional[Path] = None, *,
          min_show_ms: int = 400, fade_ms: int = 180,
          text: str = "正在启动…") -> Optional[Splash]:
    """创建并显示启动画面。**必须在导入 PySide6 之前调用。**

    返回 None 表示"这次没有启动画面"（非 Windows、资源缺失、建窗失败、
    或设了 ``FMP_NO_SPLASH=1``），调用方不必区分原因，也永远不该因此中断启动。
    """
    if os.environ.get("FMP_NO_SPLASH", "") == "1" or not _WINDOWS:
        return None
    try:
        base = Path(assets_dir) if assets_dir else Path(__file__).resolve().parent.parent / "assets"
        theme, accent = read_prefs(data_dir)
        art = load_art(base / f"splash-{theme}.dat")
        if art is None:  # 只有一张底图时也照样能起来
            art = load_art(base / f"splash-{'light' if theme == 'dark' else 'dark'}.dat")
        if art is None:
            return None
        splash = Splash(art, accent, text=text, min_show_ms=min_show_ms, fade_ms=fade_ms)
        return splash if splash.start() else None
    except Exception:
        traceback.print_exc()
        return None
