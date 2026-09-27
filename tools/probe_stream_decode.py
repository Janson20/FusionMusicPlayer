"""可行性探测（三）：QAudioDecoder 能否直接分析**网络流**。

音量均衡要覆盖在线曲目：如果解码器能直接读 https 流、并且在够用的样本到手后
``stop()`` 就能断开连接，那么在线曲目既不需要先整首下载、也不需要落临时文件。

用法::

    python tools/probe_stream_decode.py <url> [url ...]
"""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QCoreApplication, QTimer, QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

RATE = 8000


def probe(url: str, stop_after_s: float = 30.0) -> None:
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    dec = QAudioDecoder()
    fmt = QAudioFormat()
    fmt.setSampleRate(RATE)
    fmt.setChannelCount(1)
    fmt.setSampleFormat(QAudioFormat.Float)
    dec.setAudioFormat(fmt)
    dec.setSource(QUrl(url))

    got = {"n": 0, "first_ms": None, "errors": []}
    target = int(stop_after_s * RATE)

    def on_buffer():
        buf = dec.read()
        if not buf.isValid():
            return
        if got["first_ms"] is None:
            got["first_ms"] = (time.perf_counter() - t0) * 1000
        got["n"] += buf.frameCount()
        if got["n"] >= target:
            dec.stop()

    dec.bufferReady.connect(on_buffer)
    dec.finished.connect(app.quit)
    dec.error.connect(lambda e: got["errors"].append(str(e)))

    t0 = time.perf_counter()
    dec.start()
    stop = QTimer()
    stop.setSingleShot(True)
    stop.timeout.connect(app.quit)
    stop.start(20000)
    while got["n"] < target and not got["errors"] and time.perf_counter() - t0 < 20:
        app.processEvents()
        time.sleep(0.002)
    elapsed = time.perf_counter() - t0
    dec.stop()
    print(f"  {url}\n    首帧 {got['first_ms']} ms，"
          f"{got['n']} 样本（{got['n'] / RATE:.1f}s 音频），总耗时 {elapsed:.2f}s，"
          f"错误: {got['errors'] or '无'}")


def main() -> int:
    urls = sys.argv[1:] or [
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    ]
    for url in urls:
        try:
            probe(url)
        except Exception as e:  # noqa: BLE001
            print(f"  {url}\n    异常: {e!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
