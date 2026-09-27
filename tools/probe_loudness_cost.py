"""可行性探测（二）：真实 FLAC 解码 + 纯 Python 响度运算的耗时。

结论要回答两个问题：

1. ``QAudioDecoder`` 对真实无损文件（FLAC）解码到 8kHz 单声道 float 要多久；
2. 在 CPython 3.14 里对解出来的样本做 K 加权（两级 biquad）+ 400ms 分块门限
   响度，耗时是多少 —— 决定「音量均衡」能不能不依赖 numpy。

用法::

    python tools/probe_loudness_cost.py <音频文件> [音频文件...]
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

TARGET_RATE = 8000


# ── 解码 ────────────────────────────────────────────────────


def decode_mono(path_or_url: str, rate: int = TARGET_RATE, stop_after_s: float = 0.0):
    """解码成 ``(samples, seconds)``；``stop_after_s > 0`` 时够了就停。"""
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    dec = QAudioDecoder()
    fmt = QAudioFormat()
    fmt.setSampleRate(rate)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.Float)
    dec.setAudioFormat(fmt)
    src = path_or_url
    if "://" not in src:
        src = QUrl.fromLocalFile(str(Path(src).resolve())).toString()
    dec.setSource(QUrl(src))

    out: list[float] = []
    done = {"flag": False}

    def on_buffer():
        buf = dec.read()
        if not buf.isValid():
            return
        data = bytes(buf.constData())
        out.extend(memoryview(data).cast("f"))
        if stop_after_s and len(out) >= stop_after_s * rate:
            done["flag"] = True
            dec.stop()

    def on_finished():
        done["flag"] = True
        app.quit()

    dec.bufferReady.connect(on_buffer)
    dec.finished.connect(on_finished)

    t0 = time.perf_counter()
    dec.start()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(app.quit)
    timer.start(60000 if stop_after_s else 300000)
    # bufferReady 是「有数据了」，stop() 之后要靠定时器回来
    while not done["flag"]:
        app.processEvents()
        time.sleep(0.001)
    app.processEvents()
    return out, time.perf_counter() - t0


# ── 响度（EBU R128 思路的简化实现）──────────────────────────


def biquad_coeffs(kind: str, rate: int):
    """K 加权的两级 biquad 系数（RBJ cookbook + BS.1770 的近似）。"""
    if kind == "shelf":       # 高频搁架：+4dB @ ~1.5kHz（BS.1770 表 1 的近似）
        f0, gain_db, q = 1681.97, 3.999, 0.7071
        a = 10 ** (gain_db / 40)
        w = 2 * math.pi * f0 / rate
        cos_w, sin_w = math.cos(w), math.sin(w)
        alpha = sin_w / (2 * q)
        b0 = a * ((a + 1) + (a - 1) * cos_w + 2 * math.sqrt(a) * alpha)
        b1 = -2 * a * ((a - 1) + (a + 1) * cos_w)
        b2 = a * ((a + 1) + (a - 1) * cos_w - 2 * math.sqrt(a) * alpha)
        a0 = (a + 1) - (a - 1) * cos_w + 2 * math.sqrt(a) * alpha
        a1 = 2 * ((a - 1) - (a + 1) * cos_w)
        a2 = (a + 1) - (a - 1) * cos_w - 2 * math.sqrt(a) * alpha
        return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)
    # 高通：38Hz（BS.1770 用的是 38Hz 二阶高通）
    f0, q = 38.13547087602444, 0.5003270373238773
    w = 2 * math.pi * f0 / rate
    cos_w, sin_w = math.cos(w), math.sin(w)
    alpha = sin_w / (2 * q)
    b0, b1, b2 = (1 + cos_w) / 2, -(1 + cos_w), (1 + cos_w) / 2
    a0 = 1 + alpha
    a1, a2 = -2 * cos_w, 1 - alpha
    return (b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0)


def k_weight(samples: list[float], rate: int) -> list[float]:
    """两级 biquad 串联（纯 Python 紧循环）。"""
    for kind in ("highpass", "shelf"):
        b0, b1, b2, a1, a2 = biquad_coeffs(kind, rate)
        x1 = x2 = y1 = y2 = 0.0
        out = [0.0] * len(samples)
        i = 0
        for x in samples:
            y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
            x2 = x1
            x1 = x
            y2 = y1
            y1 = y
            out[i] = y
            i += 1
        samples = out
    return samples


def integrated_loudness(samples: list[float], rate: int, block_s: float = 0.4) -> float:
    """门限积分响度（LUFS）。"""
    step = max(1, rate // 10)                 # 100ms 步进 = 75% 重叠
    size = max(1, int(block_s * rate))
    loudness = []
    for start in range(0, max(0, len(samples) - size + 1), step):
        total = 0.0
        for v in samples[start:start + size]:
            total += v * v
        ms = total / size
        if ms > 0:
            loudness.append(-0.691 + 10 * math.log10(ms))
    if not loudness:
        return -70.0
    gated = [l for l in loudness if l > -70.0]
    if not gated:
        return -70.0
    rel = sum(gated) / len(gated) - 10.0
    gated = [l for l in gated if l > rel]
    if not gated:
        return -70.0
    ms = sum(10 ** ((l + 0.691) / 10) for l in gated) / len(gated)
    return -0.691 + 10 * math.log10(ms)


def main() -> int:
    targets = sys.argv[1:]
    if not targets:
        import json

        local = Path(__file__).resolve().parent.parent / "data" / "local.json"
        if local.exists():
            entries = json.loads(local.read_text(encoding="utf-8"))
            targets = [e["path"] for e in entries[:3] if Path(e.get("path", "")).exists()]
        if not targets:
            print("用法: python tools/probe_loudness_cost.py <音频文件> ...")
            return 2

    for target in targets:
        p = Path(target)
        size_mb = p.stat().st_size / 1024 / 1024 if p.exists() else 0
        print(f"\n=== {p.name} ({size_mb:.1f} MB) ===")

        samples, dec_t = decode_mono(target)
        secs = len(samples) / TARGET_RATE
        print(f"  解码: {len(samples):,} 样本 / {secs:.1f}s 音频，耗时 {dec_t:.2f}s"
              f"（{secs / max(dec_t, 1e-6):.0f}x 实时）")

        t0 = time.perf_counter()
        weighted = k_weight(samples, TARGET_RATE)
        dsp_t = time.perf_counter() - t0
        print(f"  K 加权（2×biquad 纯 Python）: {dsp_t:.2f}s "
              f"({len(samples) / max(dsp_t, 1e-6) / 1e6:.2f} M样本/s)")

        t0 = time.perf_counter()
        lufs = integrated_loudness(weighted, TARGET_RATE)
        gate_t = time.perf_counter() - t0
        peak = max((abs(v) for v in samples), default=0.0)
        print(f"  门限积分响度: {lufs:.2f} LUFS（分块耗时 {gate_t:.2f}s）"
              f"，样本峰值 {peak:.4f} ({20 * math.log10(peak or 1e-9):.2f} dBFS)")
        print(f"  合计分析耗时: {dec_t + dsp_t + gate_t:.2f}s")

        # 只分析前 60 秒的近似值，用于流媒体曲目
        head = samples[:TARGET_RATE * 60]
        t0 = time.perf_counter()
        lufs_head = integrated_loudness(k_weight(head, TARGET_RATE), TARGET_RATE)
        print(f"  仅前 60s: {lufs_head:.2f} LUFS（耗时 {time.perf_counter() - t0:.2f}s，"
              f"与全曲差 {lufs_head - lufs:+.2f} LU）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
