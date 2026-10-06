"""搜索联想的端到端验收：真界面 + 真网易云接口，打字后截图。

用法::

    python tools/probe_search_suggest_visual.py [关键词] [输出PNG]
"""

from __future__ import annotations

import faulthandler
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["FUSION_MUSIC_HOME"] = tempfile.mkdtemp(prefix="fusion_suggest_")
# 崩溃（访问违例）时把原生栈打出来，否则只能看到一个退出码
faulthandler.enable()

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl  # noqa: E402
from PySide6.QtQml import QQmlExpression  # noqa: E402

from app.application import Application  # noqa: E402


def step(text: str) -> None:
    print(f"[probe] {text}", flush=True)


class Visual(Application):
    def run(self) -> int:
        from app import paths

        self.keyword = sys.argv[1] if len(sys.argv) > 1 else "周杰"
        self.out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("search_suggest.png")

        self.engine.load(QUrl.fromLocalFile(str(paths.qml_dir() / "Main.qml")))
        roots = self.engine.rootObjects()
        if not roots:
            print("界面没起来")
            return 1
        self.window = roots[0]
        # 与 Application.run 保持一致：退出时走一趟 shutdown，**并先拆 QML 引擎**
        # （不拆的话解释器退出时析构顺序不定，会以访问违例收场）
        self.qt_app.aboutToQuit.connect(self.shutdown)
        QTimer.singleShot(1400, self.probe)
        code = self.qt_app.exec()
        self._release_engine()
        return code

    def pump(self, ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def probe(self) -> None:
        step("进入搜索页")
        self.app.go("search")
        self.pump(900)

        box = self.window.findChild(QObject, "searchInput")
        if box is None:
            print("找不到搜索框")
            self.qt_app.exit(1)
            return

        # 聚焦 + 填词：走 QML 侧（Python 直接 setProperty 不会触发 textEdited）
        step(f"填词 {self.keyword!r}")
        QQmlExpression(self.engine.rootContext(), box, f'text = "{self.keyword}"').evaluate()
        step("请求焦点")
        box.forceActiveFocus()
        step("调 suggest()")
        self.search.suggest(self.keyword)

        spent = 0
        while spent < 8000 and not self.search.suggestions:
            self.pump(200)
            spent += 200
        step(f"等到 {len(self.search.suggestions)} 条联想（{spent} ms）")
        self.pump(500)

        for item in self.search.suggestions:
            print(f"   [{item.get('from')}] {item.get('keyword')}", flush=True)

        image = self.window.grabWindow()
        image.save(str(self.out))
        step(f"截图：{self.out.resolve()}")
        # 收掉还在飞的联想请求，再退出（见 run() 里关于退出的注释）
        self.search.clearSuggestions()
        self.qt_app.exit(0)


if __name__ == "__main__":
    raise SystemExit(Visual(sys.argv[:1]).run())
