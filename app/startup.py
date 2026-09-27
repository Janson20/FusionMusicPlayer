"""启动阶段计时：进程创建 → 各阶段 → 首帧。

"启动慢"必须先能测，否则优化就是凭感觉。这里量的是**进程创建算起**的绝对时间，
所以打包引导（PyInstaller bootloader）、解释器启动、import、QML 编译全都算在内，
和用户实际等待的时间一致。

用法::

    FMP_TRACE_STARTUP=1 python main.py     # 每个阶段立刻打一行到 stderr
    python main.py                         # 只在日志里留一行汇总

外部观测（含"启动画面何时可见、主窗口何时可见"）见 ``tools/probe_startup.py``。
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from typing import List, Optional, Tuple

logger = logging.getLogger("fusion")

_EPOCH_OFFSET = 11644473600.0  # 1601-01-01 → 1970-01-01 的秒数
_lock = threading.Lock()
_marks: List[Tuple[str, float]] = []
_t0 = time.monotonic()


def _boot_offset_ms() -> float:
    """本进程从创建到现在已经过去的毫秒数；取不到就返回 0（只影响基准点）。"""
    if sys.platform != "win32":
        return 0.0
    try:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p] * 5
        kernel32.GetProcessTimes.restype = ctypes.c_int
        creation = ctypes.c_uint64()
        exit_time = ctypes.c_uint64()
        kernel = ctypes.c_uint64()
        user = ctypes.c_uint64()
        ok = kernel32.GetProcessTimes(kernel32.GetCurrentProcess(), ctypes.byref(creation),
                                      ctypes.byref(exit_time), ctypes.byref(kernel),
                                      ctypes.byref(user))
        if ok:
            return (time.time() - (creation.value / 1e7 - _EPOCH_OFFSET)) * 1000.0
    except Exception:
        pass
    return 0.0


_OFFSET_MS = _boot_offset_ms()


def elapsed_ms() -> float:
    """从**进程创建**算起的毫秒数。"""
    return _OFFSET_MS + (time.monotonic() - _t0) * 1000.0


def trace_enabled() -> bool:
    return os.environ.get("FMP_TRACE_STARTUP", "") == "1"


def mark(label: str, *, splash=None, progress: Optional[float] = None) -> float:
    """记一个阶段。给了 ``splash`` 就顺手把启动画面的状态文字/进度推上去。"""
    now = elapsed_ms()
    with _lock:
        _marks.append((label, now))
    if splash is not None:
        try:
            splash.set_status(label, progress)
        except Exception:  # 启动画面不该影响任何主流程
            pass
    if trace_enabled():
        print(f"[startup] {now:8.0f} ms  {label}", file=sys.stderr, flush=True)
    return now


def report() -> None:
    """把结果写进日志：一行汇总；开了 trace 再附完整分阶段表。"""
    with _lock:
        marks = list(_marks)
    if not marks:
        return
    logger.info("启动完成：进程创建 → 首帧 %.0f ms", marks[-1][1])
    if trace_enabled():
        for label, ms in marks:
            logger.info("  启动阶段 %8.0f ms  %s", ms, label)
