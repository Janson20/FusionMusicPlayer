#!/usr/bin/env python3
"""启动耗时探针：从"拉进程"到"启动画面可见"再到"主窗口可见"，逐段计时。

用法::

    python tools/probe_startup.py src              # python main.py（源码运行）
    python tools/probe_startup.py exe              # dist 下的打包版
    python tools/probe_startup.py src --repeat 3   # 多次取中位数

做的是**外部观测**：用 ctypes 轮询目标进程的顶层窗口，因此量到的是用户真实
感知的等待时间，不掺进程内部的自我报告。两个关键时间点：

* ``启动画面`` —— 有反馈了（在此之前用户看到的是"点了没反应"）；
* ``主窗口``   —— 真能用了。

顺带校验启动画面是否在主窗口出来后**自己退场**（卡在最上层是典型事故）。
进程内部的阶段拆分见 ``FMP_TRACE_STARTUP=1``（app/startup.py）。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER32 = ctypes.windll.user32
SPLASH_CLASS = "FusionMusicSplashWnd"
GET_CLASS_NAME = USER32.GetClassNameW
GET_CLASS_NAME.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def _windows_of(pid: int) -> list[tuple[int, str, str]]:
    """该进程所有可见顶层窗口：(hwnd, class, title)。"""
    found: list[tuple[int, str, str]] = []

    def _cb(hwnd, _lparam):
        owner = wt.DWORD()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and USER32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            GET_CLASS_NAME(hwnd, buf, 256)
            title = ctypes.create_unicode_buffer(256)
            USER32.GetWindowTextW(hwnd, title, 256)
            found.append((int(hwnd), buf.value, title.value))
        return True

    USER32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found


def _build_cmd(kind: str) -> tuple[list[str], str]:
    if kind == "src":
        return [sys.executable, str(ROOT / "main.py")], str(ROOT)
    exe = ROOT / "dist" / "FusionMusicPlayer" / "FusionMusicPlayer.exe"
    if not exe.exists():
        raise SystemExit(f"找不到打包版：{exe}")
    return [str(exe)], str(exe.parent)


def _once(kind: str) -> dict[str, float]:
    cmd, cwd = _build_cmd(kind)
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, cwd=cwd)
    result: dict[str, float] = {}
    splash_gone_at: float | None = None
    try:
        deadline = t0 + 90.0
        while time.perf_counter() < deadline:
            if proc.poll() is not None:
                raise SystemExit(f"进程提前退出，返回码 {proc.returncode}")
            names = [cls for _, cls, _title in _windows_of(proc.pid)]
            if "splash" not in result and SPLASH_CLASS in names:
                result["splash"] = (time.perf_counter() - t0) * 1000.0
            if "main" not in result and any(cls != SPLASH_CLASS for cls in names):
                result["main"] = (time.perf_counter() - t0) * 1000.0
            if "main" in result:
                if SPLASH_CLASS in names:
                    splash_gone_at = None
                elif splash_gone_at is None:
                    splash_gone_at = (time.perf_counter() - t0) * 1000.0
                if splash_gone_at is not None:
                    break
            time.sleep(0.005)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    if "main" not in result:
        raise SystemExit("90 秒内没等到主窗口")
    result["splash_gone"] = splash_gone_at if splash_gone_at is not None else -1.0
    return result


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    kind = args[0] if args else "src"
    repeat = 1
    if "--repeat" in argv:
        repeat = int(argv[argv.index("--repeat") + 1])
    if kind not in {"src", "exe"}:
        raise SystemExit("参数只能是 src 或 exe")

    rows = []
    print(f"[{kind}] 采样 {repeat} 次", flush=True)
    for i in range(repeat):
        row = _once(kind)
        rows.append(row)
        print(
            f"  第 {i + 1} 次：启动画面 {row['splash']:7.0f} ms"
            f" | 主窗口 {row['main']:7.0f} ms"
            f" | 画面退场 {row['splash_gone']:7.0f} ms",
            flush=True,
        )
        time.sleep(2.0)
    if repeat > 1:
        for key, label in (("splash", "启动画面"), ("main", "主窗口")):
            values = [r[key] for r in rows]
            print(f"  {label} 中位数 {statistics.median(values):.0f} ms"
                  f"（{min(values):.0f} ~ {max(values):.0f}）")
    stuck = [r for r in rows if r["splash_gone"] < 0]
    if stuck:
        print("  ！启动画面在主窗口出现后没有退场，需要排查")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
