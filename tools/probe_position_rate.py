"""量一下 ``QMediaPlayer.positionChanged`` 的实际触发频率。

动态歌词要靠播放位置推进填充，先得知道位置信号的粒度：如果后端一秒才发
一次，界面上的"逐字填充"就会一跳一跳，得自己插值补帧。

用法::

    python tools/probe_position_rate.py [秒数] [输出文件]
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: E402


def write_wav(path: Path, seconds: float, rate: int = 44100) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = int(seconds * rate)
        w.writeframes(struct.pack("<%dh" % frames, *([0] * frames)))


#: 必须留住引用：QGuiApplication 被 Python 回收掉之后 Qt 就没了事件循环
_QT_APP = None


def main() -> int:
    global _QT_APP
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("probe_position_rate.txt")
    _QT_APP = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    tmp = Path(tempfile.mkdtemp(prefix="fusion_pos_")) / "silent.wav"
    write_wav(tmp, seconds)

    player = QMediaPlayer()
    output = QAudioOutput()
    player.setAudioOutput(output)
    output.setVolume(0.0)

    stamps: list[tuple[float, int]] = []
    start = time.perf_counter()

    def on_position(ms: int) -> None:
        stamps.append((time.perf_counter() - start, int(ms)))

    player.positionChanged.connect(on_position)
    status_log: list[str] = []

    def on_status(status) -> None:
        status_log.append(f"{time.perf_counter() - start:6.3f}s status={status} "
                          f"state={player.playbackState()} error={player.error()}")
    player.mediaStatusChanged.connect(on_status)
    player.errorOccurred.connect(lambda e, m: status_log.append(f"error {e}: {m}"))

    player.setSource(QUrl.fromLocalFile(str(tmp)))
    player.play()

    loop = QEventLoop()
    QTimer.singleShot(int(seconds * 1000) + 500, loop.quit)
    loop.exec()

    deltas = [round((stamps[i][0] - stamps[i - 1][0]) * 1000, 1) for i in range(1, len(stamps))]
    out = [
        f"播放 {seconds} 秒，positionChanged 触发 {len(stamps)} 次",
        f"平均间隔: {sum(deltas) / len(deltas):.1f} ms" if deltas else "没有触发",
        f"最小/最大间隔: {min(deltas) if deltas else '-'} / {max(deltas) if deltas else '-'} ms",
        f"位置步进(ms): {[stamps[i][1] - stamps[i - 1][1] for i in range(1, len(stamps))][:20]}",
        "",
        "媒体状态变化：",
        *status_log,
    ]
    target.write_text("\n".join(str(x) for x in out), encoding="utf-8")
    print(f"已写入 {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
