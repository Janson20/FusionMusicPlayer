"""启动画面用到的 Win32 底层：常量、结构体、函数原型与几个小工具。

单独成文件是为了让 :mod:`app.splash` 只关心"画什么、什么时候收"，
而不是淹没在 ctypes 的原型声明里。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

# ── 窗口样式 / 消息 ─────────────────────────────────────────
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020  # 点穿：启动画面全程不接受鼠标
WS_EX_TOOLWINDOW = 0x00000080   # 不在任务栏留按钮
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000   # 不抢焦点
SW_SHOWNOACTIVATE = 4
ULW_ALPHA = 0x00000002
AC_SRC_OVER, AC_SRC_ALPHA = 0x00, 0x01
WM_DESTROY, WM_CLOSE, WM_TIMER, WM_ERASEBKGND, WM_NCHITTEST = 2, 0x0010, 0x0113, 0x0014, 0x0084
HTTRANSPARENT = -1
SPI_GETWORKAREA = 0x0030
IDC_ARROW = 32512
NULL_PEN = 8
LOGPIXELSX = 88
DIB_RGB_COLORS, BI_RGB, SRCCOPY = 0, 0, 0x00CC0020
HALFTONE = 4
TRANSPARENT = 1
DT_CENTER, DT_VCENTER, DT_SINGLELINE, DT_NOPREFIX, DT_END_ELLIPSIS = 0x1, 0x4, 0x20, 0x800, 0x8000
DEFAULT_CHARSET, CLEARTYPE_QUALITY = 1, 5
OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS, DEFAULT_PITCH, FF_DONTCARE = 0, 0, 0, 0
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HANDLE), ("hIcon", wt.HANDLE), ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HANDLE), ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HANDLE),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class BLENDFUNCTION(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

_PROTOTYPES = (
    (user32, "DefWindowProcW", [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM], ctypes.c_ssize_t),
    (user32, "RegisterClassExW", [ctypes.POINTER(WNDCLASSEXW)], wt.WORD),
    (user32, "CreateWindowExW",
     [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
      ctypes.c_int, wt.HWND, wt.HANDLE, wt.HANDLE, ctypes.c_void_p], wt.HWND),
    (user32, "DestroyWindow", [wt.HWND], wt.BOOL),
    (user32, "ShowWindow", [wt.HWND, ctypes.c_int], wt.BOOL),
    (user32, "LoadCursorW", [wt.HANDLE, wt.LPCWSTR], wt.HANDLE),
    (user32, "GetDC", [wt.HWND], wt.HANDLE),
    (user32, "ReleaseDC", [wt.HWND, wt.HANDLE], ctypes.c_int),
    (user32, "GetSystemMetrics", [ctypes.c_int], ctypes.c_int),
    (user32, "SetTimer", [wt.HWND, ctypes.c_size_t, wt.UINT, ctypes.c_void_p], ctypes.c_size_t),
    (user32, "KillTimer", [wt.HWND, ctypes.c_size_t], wt.BOOL),
    (user32, "GetMessageW", [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT], wt.BOOL),
    (user32, "TranslateMessage", [ctypes.POINTER(wt.MSG)], wt.BOOL),
    (user32, "DispatchMessageW", [ctypes.POINTER(wt.MSG)], ctypes.c_ssize_t),
    (user32, "PostQuitMessage", [ctypes.c_int], None),
    (user32, "DrawTextW", [wt.HANDLE, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.RECT), wt.UINT],
     ctypes.c_int),
    (user32, "SystemParametersInfoW", [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT], wt.BOOL),
    (user32, "UpdateLayeredWindow",
     [wt.HWND, wt.HANDLE, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE), wt.HANDLE,
      ctypes.POINTER(wt.POINT), wt.DWORD, ctypes.POINTER(BLENDFUNCTION), wt.DWORD], wt.BOOL),
    (gdi32, "CreateCompatibleDC", [wt.HANDLE], wt.HANDLE),
    (gdi32, "DeleteDC", [wt.HANDLE], wt.BOOL),
    (gdi32, "SelectObject", [wt.HANDLE, wt.HANDLE], wt.HANDLE),
    (gdi32, "DeleteObject", [wt.HANDLE], wt.BOOL),
    (gdi32, "GetStockObject", [ctypes.c_int], wt.HANDLE),
    (gdi32, "CreateDIBSection",
     [wt.HANDLE, ctypes.POINTER(BITMAPINFO), wt.UINT, ctypes.POINTER(ctypes.c_void_p),
      wt.HANDLE, wt.DWORD], wt.HANDLE),
    (gdi32, "CreateSolidBrush", [wt.DWORD], wt.HANDLE),
    (gdi32, "RoundRect",
     [wt.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
      ctypes.c_int], wt.BOOL),
    (gdi32, "StretchBlt",
     [wt.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HANDLE,
      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.DWORD], wt.BOOL),
    (gdi32, "SetStretchBltMode", [wt.HANDLE, ctypes.c_int], ctypes.c_int),
    (gdi32, "SetBkMode", [wt.HANDLE, ctypes.c_int], ctypes.c_int),
    (gdi32, "SetTextColor", [wt.HANDLE, wt.DWORD], wt.DWORD),
    (gdi32, "CreateFontW",
     [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR], wt.HANDLE),
    (gdi32, "GetTextFaceW", [wt.HANDLE, ctypes.c_int, wt.LPWSTR], ctypes.c_int),
    (gdi32, "GetDeviceCaps", [wt.HANDLE, ctypes.c_int], ctypes.c_int),
    (kernel32, "GetModuleHandleW", [wt.LPCWSTR], wt.HANDLE),
)

for _dll, _name, _args, _ret in _PROTOTYPES:
    _fn = getattr(_dll, _name)
    _fn.argtypes, _fn.restype = _args, _ret
del _dll, _name, _args, _ret, _fn


def colorref(rgb: tuple[int, int, int]) -> int:
    """RGB → COLORREF(0x00BBGGRR)。"""
    return (rgb[2] << 16) | (rgb[1] << 8) | rgb[0]


def dpi_scale() -> float:
    """相对 96 DPI 的缩放倍率。

    先声明进程 DPI 感知：不声明的话系统会把我们按 96 DPI 画的像素再拉一遍，
    高 DPI 屏上启动画面会糊。声明失败（打包清单里已声明过）就按实际 DPI 取值。
    """
    try:
        user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except Exception:
        pass
    probes = (
        lambda: user32.GetDpiForSystem(),
        lambda: gdi32.GetDeviceCaps(user32.GetDC(0), LOGPIXELSX),
    )
    for probe in probes:
        try:
            dpi = int(probe())
        except Exception:
            continue
        if dpi > 0:
            return max(1.0, min(4.0, dpi / 96.0))
    return 1.0


def alpha_blend(src_dc: int, src_size: tuple[int, int], dst_dc: int,
                dst_size: tuple[int, int]) -> bool:
    """msimg32!AlphaBlend：GDI 里唯一能连 alpha 通道一起缩放的位块传送。"""
    try:
        fn = ctypes.WinDLL("msimg32").AlphaBlend
    except OSError:
        return False
    fn.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                   wt.HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                   BLENDFUNCTION]
    fn.restype = wt.BOOL
    return bool(fn(dst_dc, 0, 0, dst_size[0], dst_size[1],
                   src_dc, 0, 0, src_size[0], src_size[1],
                   BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)))


def pick_font(dc: int, candidates: tuple[str, ...], height_px: int) -> int:
    """按候选顺序挑一个真实存在的字体。

    GDI 在字体缺失时会**静默替换**成别的字体（中文还可能变成方块），
    所以建完字体用 ``GetTextFaceW`` 读回真实字面名对一下，别猜。
    """
    for name in candidates:
        font = gdi32.CreateFontW(
            -abs(int(height_px)), 0, 0, 0, 400, 0, 0, 0, DEFAULT_CHARSET,
            OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
            DEFAULT_PITCH | FF_DONTCARE, name,
        )
        if not font:
            continue
        buffer = ctypes.create_unicode_buffer(64)
        previous = gdi32.SelectObject(dc, font)
        gdi32.GetTextFaceW(dc, 64, buffer)
        gdi32.SelectObject(dc, previous)
        if buffer.value.strip().lower() == name.lower():
            return font
        gdi32.DeleteObject(font)
    return 0
