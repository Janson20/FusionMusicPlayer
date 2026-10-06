"""把真实的逐字歌词灌进界面，按几个播放位置截图，肉眼验收填充效果。

用的是实测拿到的网易云 yrc（海屿你 / 1973665667），跑的是**真界面**
（Main.qml + 展开播放页），不是示意图。

用法::

    python tools/probe_karaoke_visual.py <输出目录>
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["FUSION_MUSIC_HOME"] = tempfile.mkdtemp(prefix="fusion_visual_")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402

from app.application import Application  # noqa: E402

# 实测响应片段（2026-10，网易云 /api/song/lyric 带 yv=-1）
LRC = """[00:00.00] 作词 : Fanko冯思源
[00:13.47]从不主动示弱
[00:17.73]我们的过去
[00:19.56]分分合合太多
[00:24.09]伤人的话难说
"""
YRC = (
    "[0,1000](0,1000,0) 作词 : Fanko冯思源\n"
    "[13010,4780](13010,660,0)从(13670,670,0)不(14340,30,0) (14370,480,0)主"
    "(14850,610,0)动(15460,30,0) (15490,330,0)示(15820,1070,0)弱(16890,900,0) \n"
    "[17790,1770](17790,170,0)我(17960,450,0)们(18410,290,0)的(18700,470,0)过(19170,390,0)去\n"
    "[19560,4580](19560,450,0)分(20010,670,0)分(20680,400,0)合(21080,820,0)合(21900,60,0) "
    "(21960,430,0)太(22390,1400,0)多(23790,350,0) \n"
    "[24140,3180](24140,250,0)伤(24390,400,0)人(24790,120,0)的(24910,450,0)话(25360,420,0)"
    "难(25780,1320,0)说(27100,220,0) \n"
)

#: 要截图的播放位置（毫秒）——第一行在 13010 起唱，取几个关键点
POSITIONS = [13470, 14340, 15000, 16600]


class Visual(Application):
    def run(self) -> int:
        from app import paths

        out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("karaoke_shots")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.engine.load(QUrl.fromLocalFile(str(paths.qml_dir() / "Main.qml")))
        roots = self.engine.rootObjects()
        if not roots:
            print("界面没起来")
            return 1
        self.window = roots[0]

        QTimer.singleShot(1200, lambda: self.shoot(out_dir))
        code = self.qt_app.exec()
        # 与 Application.run 一样先拆 QML 引擎：重写了 run() 的探针很容易漏掉这步，
        # 漏掉就会在退出瞬间访问违例（0xC0000005），弹一句 "python has stopped working"
        self._release_engine()
        return code

    def pump(self, ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def shoot(self, out_dir: Path) -> None:
        from app.core.lyrics import Lyrics

        lyrics = Lyrics()
        lyrics.parse(LRC)
        adopted = lyrics.set_words(YRC)
        pseudo = lyrics.apply_pseudo()
        print(f"贴上逐字 {adopted} 行，补伪动态 {pseudo} 行")

        self.player._lyrics = lyrics
        self.player._lyric_index = 1
        self.player.lyricChanged.emit()
        self.player.lyricIndexChanged.emit()

        self.app.setExpanded(True)
        self.pump(1200)

        for ms in POSITIONS:
            self.show_at(lyrics, ms)
            self.save(out_dir / f"yrc_{ms}ms.png", ms)

        # 换个「只有逐行歌词」的场景：伪动态兜底的样子
        pseudo_only = Lyrics()
        pseudo_only.parse(LRC)
        made = pseudo_only.apply_pseudo()
        self.player._lyrics = pseudo_only
        self.player.lyricChanged.emit()
        self.pump(600)
        print(f"伪动态场景：{made} 行")
        for ms in (14000, 15000):
            self.show_at(pseudo_only, ms)
            self.save(out_dir / f"pseudo_{ms}ms.png", ms)

        # 用 exit(0) 而不是 quit()：托盘图标露过面之后 quit() 会被 Qt 吞掉
        # （与 bridges/app.py:quitApplication 同一个坑），进程会挂在这儿不退出
        self.qt_app.exit(0)

    def show_at(self, lyrics, ms: int) -> None:
        self.player._position_ms = ms
        self.player._lyric_index = lyrics.index_at(ms)
        self.player._lyric_progress = lyrics.char_progress(ms)
        self.player.lyricIndexChanged.emit()
        self.player.lyricProgressChanged.emit()
        self.pump(500)

    def save(self, target: Path, ms: int) -> None:
        image = self.window.grabWindow()
        image.save(str(target))
        print(f"{ms} ms（当前行 {self.player._lyric_index}，"
              f"进度 {self.player._lyric_progress:.2f} 字）→ {target.name}")


if __name__ == "__main__":
    raise SystemExit(Visual(sys.argv[:1]).run())
