"""启动画面窗口：独立线程 + 分层窗口 + GDI 绘制。

从 :mod:`app.splash` 拆出来的：那边只剩"读资源 / 定主题 / 对外工厂"，
真正的窗口与绘图逻辑（约 300 行）都在这里，改画面时只看这一个文件。

线程模型
--------
窗口建在**自己的线程**上、自带消息循环：主线程该 import 什么继续 import，
两边不互堵（``GetMessageW`` 由 ctypes 调用，期间释放 GIL）。所有 GDI/user32
调用都只发生在该线程；主线程只通过加锁的状态变量传话（状态文字、进度目标、
"该收了"），由 16 ms 的 WM_TIMER 自己取用并重绘。

非 Windows 上 ``ctypes`` 没有 ``WinDLL``，整个 Win32 层拿不到 —— 这时
``WINDOWS`` 为 False，调用方（``app.splash.start``）直接当"没有启动画面"，
入口照常跑。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import threading
import time
import traceback
from typing import TYPE_CHECKING, Optional

try:  # pragma: no cover - 非 Windows 上整块都拿不到
    from .splash_win32 import (
        BI_RGB, DIB_RGB_COLORS, DT_CENTER, DT_END_ELLIPSIS, DT_NOPREFIX, DT_SINGLELINE,
        DT_VCENTER, HALFTONE, HTTRANSPARENT, IDC_ARROW, NULL_PEN, SPI_GETWORKAREA, SRCCOPY,
        SW_SHOWNOACTIVATE, TRANSPARENT, ULW_ALPHA, WM_CLOSE, WM_DESTROY, WM_ERASEBKGND,
        WM_NCHITTEST, WM_TIMER, WS_EX_LAYERED, WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW,
        WS_EX_TOPMOST, WS_EX_TRANSPARENT, WS_POPUP, BITMAPINFO, BITMAPINFOHEADER,
        BLENDFUNCTION, WNDCLASSEXW, WNDPROC, alpha_blend, colorref, dpi_scale, gdi32,
        kernel32, pick_font, user32,
    )

    WINDOWS = True
except Exception:  # noqa: BLE001 - 非 Windows：没有启动画面，但入口必须照常跑
    WINDOWS = False

if TYPE_CHECKING:  # 只为注解服务，运行时不导入（避免与 app.splash 循环导入）
    from .splash import Art

__all__ = ["Splash", "WINDOWS"]

CLASS_NAME = "FusionMusicSplashWnd"
TITLE = "Fusion Music Player"
FONT_CANDIDATES = ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")
HARD_TIMEOUT_S = 45.0  # 主流程万一没来收，别让画面永远压在最上层
CREEP_CAP = 0.97  # 没有新里程碑时进度条最多自行爬到这儿


class Splash:
    """启动画面句柄。公开方法可在任意线程调用，且都不会抛异常。"""

    def __init__(self, art: Art, accent: tuple[int, int, int], *, text: str = "正在启动…",
                 progress: float = 0.03, min_show_ms: int = 400, fade_ms: int = 180) -> None:
        self._art = art
        self._accent = colorref(accent)
        self._min_show_ms = max(0, int(min_show_ms))
        self._fade_ms = max(0, int(fade_ms))
        self._lock = threading.Lock()
        self._text = str(text)
        self._target = max(0.0, min(1.0, float(progress)))
        self._finish_at: Optional[float] = None
        self._quit = False
        self._shown = threading.Event()
        self._started = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="fmp-splash", daemon=True)
        # 以下仅启动画面线程访问
        self._hwnd = 0
        self._proc = None
        self._view: Optional[memoryview] = None
        self._base = b""
        self._mem_dc = 0
        self._screen_dc = 0
        self._old_bitmap = 0
        self._scale = 1.0
        self._win_size = (1, 1)
        self._pos = (0, 0)
        self._title_font = 0
        self._status_font = 0
        self._brush = 0
        self._shown_progress = 0.0
        self._drawn_text = ""
        self._alpha = 255
        self._fading = False
        self._ff: dict[int, bytes] = {}

    # ── 外部接口 ────────────────────────────────────────────

    def start(self, wait_ms: int = 300) -> bool:
        """起线程并等它上屏（等不到也照样返回 True，主流程不该被拖住）。"""
        try:
            self._thread.start()
        except Exception:
            return False
        self._shown.wait(max(0.0, wait_ms / 1000.0))
        return True

    def set_status(self, text: str, progress: Optional[float] = None) -> None:
        """更新状态文字 / 进度目标值（画面会缓动过去，不会跳）。"""
        with self._lock:
            self._text = str(text)
            if progress is not None:
                self._target = max(self._target, max(0.0, min(1.0, float(progress))))

    def finish(self) -> None:
        """首帧已到：让进度条走满，并在满足最短显示时长后淡出。"""
        with self._lock:
            self._target = 1.0
            if self._finish_at is None:
                rest = self._min_show_ms - (time.monotonic() - self._started) * 1000.0
                self._finish_at = time.monotonic() + max(0.0, rest) / 1000.0

    def close(self, join_timeout: float = 1.5) -> None:
        """立即收掉（不淡出）。退出路径的兜底，可重复调用。"""
        with self._lock:
            self._quit = True
        if self._thread.is_alive():
            self._thread.join(join_timeout)

    # ── 启动画面线程 ────────────────────────────────────────

    def _run(self) -> None:
        handles: list[int] = []
        try:
            self._scale = dpi_scale()
            if not self._create_window():
                return
            self._screen_dc = user32.GetDC(0)
            self._mem_dc = gdi32.CreateCompatibleDC(self._screen_dc)
            dib, bits = self._create_dib()
            handles.append(dib)
            self._old_bitmap = gdi32.SelectObject(self._mem_dc, dib)
            ctypes.memset(bits, 0, self._win_size[0] * self._win_size[1] * 4)
            self._view = memoryview(
                (ctypes.c_char * (self._win_size[0] * self._win_size[1] * 4)).from_address(bits)
            ).cast("B")
            self._base = self._build_base()
            self._title_font = pick_font(self._mem_dc, FONT_CANDIDATES,
                                         self._art.title_px * self._scale)
            self._status_font = pick_font(self._mem_dc, FONT_CANDIDATES,
                                          self._art.status_px * self._scale)
            handles += [self._title_font, self._status_font]
            self._brush = gdi32.CreateSolidBrush(self._accent)
            handles.append(self._brush)
            if not self._title_font or not self._status_font or not self._brush:
                raise OSError("字体/画笔创建失败")
            self._render()
            user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
            self._shown.set()
            user32.SetTimer(self._hwnd, 1, 16, None)
            self._loop()
        except Exception:
            traceback.print_exc()
        finally:
            self._shown.set()
            if self._view is not None:
                self._view.release()
                self._view = None
            if self._mem_dc and self._old_bitmap:
                # 先把它选出去再删：仍被 DC 选中的位图删除行为是未定义的
                try:
                    gdi32.SelectObject(self._mem_dc, self._old_bitmap)
                except Exception:
                    pass
            for handle in handles:
                if handle:
                    try:
                        gdi32.DeleteObject(handle)
                    except Exception:
                        pass
            if self._mem_dc:
                try:
                    gdi32.DeleteDC(self._mem_dc)
                except Exception:
                    pass
            if self._screen_dc:
                try:
                    user32.ReleaseDC(0, self._screen_dc)
                except Exception:
                    pass

    def _create_window(self) -> bool:
        width = max(1, round(self._art.width * self._scale))
        height = max(1, round(self._art.height * self._scale))
        self._win_size = (width, height)
        work = wt.RECT()
        if not user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(work), 0):
            work = wt.RECT(0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
        self._pos = ((work.left + work.right - width) // 2,
                     (work.top + work.bottom - height) // 2)
        self._proc = WNDPROC(self._wnd_proc)  # 必须留引用，否则回调被回收会崩
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(self._proc, ctypes.c_void_p)
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hCursor = user32.LoadCursorW(0, wt.LPCWSTR(IDC_ARROW))
        wc.lpszClassName = CLASS_NAME
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            return False
        style = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
                 | WS_EX_TOPMOST | WS_EX_NOACTIVATE)
        self._hwnd = user32.CreateWindowExW(
            style, CLASS_NAME, TITLE, WS_POPUP, self._pos[0], self._pos[1], width, height,
            0, 0, wc.hInstance, None,
        )
        return bool(self._hwnd)

    def _create_dib(self) -> tuple[int, int]:
        width, height = self._win_size
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # 负数 = 自上而下，与 .dat 的行序一致
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        dib = gdi32.CreateDIBSection(self._mem_dc, ctypes.byref(info), DIB_RGB_COLORS,
                                     ctypes.byref(bits), 0, 0)
        if not dib or not bits.value:
            raise OSError("CreateDIBSection 失败")
        return dib, bits.value

    def _build_base(self) -> bytes:
        """把 2 倍底图缩放到物理尺寸，读回来当作每帧的"干净底"。"""
        art_w, art_h = self._art.art_size
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = art_w
        info.bmiHeader.biHeight = -art_h
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bits = ctypes.c_void_p()
        src_dib = gdi32.CreateDIBSection(self._mem_dc, ctypes.byref(info), DIB_RGB_COLORS,
                                         ctypes.byref(bits), 0, 0)
        if not src_dib or not bits.value:
            raise OSError("底图 DIB 创建失败")
        src_dc = gdi32.CreateCompatibleDC(self._screen_dc)
        gdi32.SelectObject(src_dc, src_dib)
        try:
            ctypes.memmove(bits.value, self._art.pixels, len(self._art.pixels))
            if not alpha_blend(src_dc, self._art.art_size, self._mem_dc, self._win_size):
                # AlphaBlend 不可用时的退路：普通拉伸（透明边缘会略糙，但画面还在）
                gdi32.SetStretchBltMode(self._mem_dc, HALFTONE)
                gdi32.StretchBlt(self._mem_dc, 0, 0, self._win_size[0], self._win_size[1],
                                 src_dc, 0, 0, art_w, art_h, SRCCOPY)
            return bytes(self._view)
        finally:
            gdi32.DeleteDC(src_dc)
            gdi32.DeleteObject(src_dib)

    def _scaled_rect(self, rect: tuple[int, int, int, int]):
        x, y, w, h = rect
        s = self._scale
        return wt.RECT(round(x * s), round(y * s), round((x + w) * s), round((y + h) * s))

    def _set_alpha(self, rect) -> None:
        """把 rect 内的 alpha 补回 255。

        GDI 画文字/图形时不维护 32bpp 位图的 alpha（写进去的是 0），
        分层窗口按预乘 alpha 合成，不补就会"画了个透明字"。
        这些 rect 都在卡片不透明区域内部，所以直接补 255 是对的。
        """
        view = self._view
        if view is None:
            return
        x, y, w = rect.left, rect.top, rect.right - rect.left
        ones = self._ff.get(w)
        if ones is None:
            ones = self._ff[w] = b"\xff" * w
        stride = self._win_size[0] * 4
        for row in range(y, rect.bottom):
            start = row * stride + x * 4 + 3
            view[start:start + w * 4:4] = ones

    def _render(self) -> None:
        dc = self._mem_dc
        self._view[:] = self._base
        gdi32.SetBkMode(dc, TRANSPARENT)
        title = self._scaled_rect(self._art.title_rect)
        gdi32.SetTextColor(dc, self._art.title_color)
        previous = gdi32.SelectObject(dc, self._title_font)
        user32.DrawTextW(dc, TITLE, -1, ctypes.byref(title),
                         DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX)
        if self._drawn_text:
            status = self._scaled_rect(self._art.status_rect)
            gdi32.SelectObject(dc, self._status_font)
            gdi32.SetTextColor(dc, self._art.status_color)
            user32.DrawTextW(dc, self._drawn_text, -1, ctypes.byref(status),
                             DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX | DT_END_ELLIPSIS)
            self._set_alpha(status)
        gdi32.SelectObject(dc, previous)
        self._set_alpha(title)

        bx, by, bw, bh = self._art.bar_rect
        filled = round(bw * self._shown_progress)
        if filled > 1:
            bar = self._scaled_rect((bx, by, filled, bh))
            pen = gdi32.SelectObject(dc, gdi32.GetStockObject(NULL_PEN))
            brush = gdi32.SelectObject(dc, self._brush)
            gdi32.RoundRect(dc, bar.left, bar.top, bar.right, bar.bottom,
                            bar.bottom - bar.top, bar.bottom - bar.top)
            gdi32.SelectObject(dc, brush)
            gdi32.SelectObject(dc, pen)
            self._set_alpha(bar)
        self._paint()

    def _paint(self) -> None:
        size = wt.SIZE(*self._win_size)
        src = wt.POINT(0, 0)
        dst = wt.POINT(*self._pos)
        blend = BLENDFUNCTION(0, 0, self._alpha, 1)  # AC_SRC_OVER / AC_SRC_ALPHA
        user32.UpdateLayeredWindow(self._hwnd, self._screen_dc, ctypes.byref(dst),
                                   ctypes.byref(size), self._mem_dc, ctypes.byref(src),
                                   0, ctypes.byref(blend), ULW_ALPHA)

    def _on_tick(self) -> None:
        now = time.monotonic()
        with self._lock:
            text, target, finish_at, quit_now = self._text, self._target, self._finish_at, self._quit
        if quit_now:
            self._destroy()
            return
        if finish_at is None and now - self._started > HARD_TIMEOUT_S:
            self.finish()
            finish_at = now
        dirty = False
        if self._shown_progress < target:  # 缓动：永远朝目标走，看着不像卡住
            step = max(0.004, (target - self._shown_progress) * 0.12)
            self._shown_progress = min(target, self._shown_progress + step)
            dirty = True
        elif finish_at is None and self._shown_progress < CREEP_CAP:
            # 两个里程碑之间可能隔着 1 秒以上（QML 编译），条子完全不动会被当成死机，
            # 所以没有新目标时也让它缓慢前移 —— 上限留出余量，别提前"走满"。
            self._shown_progress = min(CREEP_CAP, self._shown_progress + 0.003)
            dirty = True
        if finish_at is not None and now >= finish_at:
            self._fading = True
        if self._fading:
            self._alpha = max(0, self._alpha - max(1, round(255 * 16 / max(1, self._fade_ms))))
            dirty = True
            if self._alpha <= 0:
                self._destroy()
                return
        if text != self._drawn_text:
            self._drawn_text = text
            dirty = True
        if dirty:
            self._render()

    def _destroy(self) -> None:
        hwnd, self._hwnd = self._hwnd, 0
        if hwnd:
            user32.KillTimer(hwnd, 1)
            user32.DestroyWindow(hwnd)  # → WM_DESTROY → PostQuitMessage

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TIMER:
                self._on_tick()
                return 0
            if msg == WM_ERASEBKGND:
                return 1
            if msg == WM_NCHITTEST:
                return HTTRANSPARENT
            if msg == WM_CLOSE:
                return 0  # 启动期间不允许取消
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            traceback.print_exc()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _loop(self) -> None:
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
