"""可行性探测：QAudioDecoder 能否把音频解码成「低采样率单声道 PCM」。

用途：音量均衡需要对曲目做响度分析。Qt 的 QMediaPlayer 不暴露 PCM，
QAudioDecoder 是 Qt 自带的解码入口；这里确认三点：

1. 能解出 PCM（后端、状态机是否走得通）；
2. ``setAudioFormat()`` 请求降采样 / 单声道 / float 是否被后端兑现
   （兑现了才可能在**纯 Python** 里做完 K 加权 + 分块响度，不需要 numpy）；
3. 每帧的样本布局（float 交错 / planar），以及解码耗时与实时率的关系。

用法::

    python tools/probe_audiodecoder.py [音频文件]
"""

from __future__ import annotations

import math
import struct
import sys
import time
import wave
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat


def make_wav(path: Path, seconds: float = 5.0, rate: int = 44100) -> Path:
    """造一个 440Hz + 3kHz 的立体声 WAV，用来验证解码链路。"""
    frames = bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        v = 0.5 * math.sin(2 * math.pi * 440 * t) + 0.2 * math.sin(2 * math.pi * 3000 * t)
        s = int(max(-1.0, min(1.0, v)) * 32767)
        frames += struct.pack("<hh", s, s)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


def probe(path: Path, want: QAudioFormat | None) -> dict:
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    dec = QAudioDecoder()
    if want is not None:
        dec.setAudioFormat(want)
    dec.setSource(QUrl.fromLocalFile(str(path)))

    state = {"buffers": 0, "frames": 0, "samples": 0, "bytes": 0, "errors": [], "fmt": None}

    def on_buffer():
        buf = dec.read()
        if not buf.isValid():
            return
        state["buffers"] += 1
        state["frames"] += buf.frameCount()
        state["bytes"] += buf.byteCount()
        f = buf.format()
        state["fmt"] = (f.sampleRate(), f.channelCount(), f.sampleFormat().name)
        state["samples"] += buf.sampleCount()

    def on_finished():
        app.quit()

    dec.bufferReady.connect(on_buffer)
    dec.finished.connect(on_finished)
    dec.error.connect(lambda e: state["errors"].append(str(e)))

    t0 = time.perf_counter()
    dec.start()
    QTimer.singleShot(30000, app.quit)
    app.exec()
    state["elapsed"] = time.perf_counter() - t0
    state["decoder_error"] = dec.error()
    return state


def main() -> int:
    if len(sys.argv) > 1:
        audio = Path(sys.argv[1])
    else:
        tmp = Path(__file__).resolve().parent.parent / "data" / "cache"
        tmp.mkdir(parents=True, exist_ok=True)
        audio = make_wav(tmp / "_probe_tone.wav")

    print(f"文件: {audio} ({audio.stat().st_size / 1024:.0f} KB)")

    print("\n[1] 不指定格式（后端默认输出）")
    print("   ", probe(audio, None))

    want = QAudioFormat()
    want.setSampleRate(8000)
    want.setChannelCount(1)
    want.setSampleFormat(QAudioFormat.Float)
    print("\n[2] 请求 8kHz / 单声道 / float32")
    print("   ", probe(audio, want))

    want2 = QAudioFormat()
    want2.setSampleRate(48000)
    want2.setChannelCount(2)
    want2.setSampleFormat(QAudioFormat.Int16)
    print("\n[3] 请求 48kHz / 立体声 / int16")
    print("   ", probe(audio, want2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
