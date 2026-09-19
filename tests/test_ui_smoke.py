"""UI 冒烟测试：启动真实 QML 界面并校验窗口与导航行为。

覆盖几个曾经真实出现过的缺陷：
1. ``FluWindow`` 的基类 ``Component.onCompleted`` 会无条件 ``show()``，
   导致设置 / 登录窗口跟着主窗口一起弹出来；
2. ``FluWindow.closeDestory`` 默认为 true，关闭即析构，之后 QML 里的 id
   变成已释放对象，再次调用 ``showWindow()`` 会抛
   ``Cannot call method 'showWindow' of null``；
3. 歌单详情页左上角「返回」发出的 ``closeRequested`` 没有接到任何地方，
   点了没反应（``discover.detailId`` 一直是空不了）；
4. 展开播放页（``panels/NowPlayingPanel.qml``）：空白处会把鼠标事件放过去、
   点到底下的导航栏，隐藏歌词后封面区赖在左边，歌词写死靠左。

无显示环境（CI）下需要一个虚拟屏幕::

    xvfb-run -a python tests/test_ui_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 用独立的数据目录，避免污染真实配置
os.environ["FUSION_MUSIC_HOME"] = tempfile.mkdtemp(prefix="fusion_uitest_")

from PySide6.QtCore import (  # noqa: E402
    QEventLoop,
    QObject,
    QPoint,
    QPointF,
    Qt,
    QTimer,
    QUrl,
    qInstallMessageHandler,
)
from PySide6.QtQml import QQmlExpression  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.application import Application  # noqa: E402

MAIN_TITLE = "Fusion Music Player"
SETTINGS_TITLE = "设置"
LOGIN_TITLE = "登录网易云音乐"

FAILS: list[str] = []

# 捕获 Qt 自己的日志。「Parameter "x" is not declared. Injection of parameters
# into signal handlers is deprecated」这类警告走的是 qt.qml.context 分类，
# 不会出现在 QQmlApplicationEngine.warnings 里，只能从这里抓。
QT_MESSAGES: list[str] = []


def _qt_message_handler(mode, context, message):
    QT_MESSAGES.append(str(message))


class UiProbe(Application):
    def run(self) -> int:
        from app import paths

        self.warnings: list[str] = []
        self.engine.warnings.connect(self._on_warn)
        self.engine.load(QUrl.fromLocalFile(str(paths.qml_dir() / "Main.qml")))
        roots = self.engine.rootObjects()
        if not roots:
            check("QML 加载", False, "rootObjects 为空")
            return self._finish()
        check("QML 加载", True)
        self.window = roots[0]

        QTimer.singleShot(1200, self.step_startup)
        return self.qt_app.exec()

    # ── 工具 ────────────────────────────────────────────────
    def _on_warn(self, ws):
        self.warnings.extend(w.toString() for w in ws)

    def pump(self, ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def visible(self) -> list[str]:
        return sorted(w.title() for w in self.qt_app.allWindows() if w.isVisible())

    def find(self, needle: str):
        for w in self.qt_app.allWindows():
            if needle in w.title():
                return w
        return None

    def eval_js(self, expr: str) -> tuple[bool, str]:
        """执行表达式，返回 ``(是否有错误, 错误信息)``。

        注意 PySide6 的 ``QQmlExpression.evaluate()`` 返回的是
        ``(值, 是否 undefined)`` 而不是 ``(值, 是否有错误)`` ——
        void 调用（如 ``app.openSettings()``）的值就是 undefined，
        不能拿它当作「出错」。
        """
        e = QQmlExpression(self.engine.rootContext(), self.window, expr)
        e.evaluate()
        return (True, e.error().toString()) if e.hasError() else (False, "")

    def eval_value(self, expr: str, default=None):
        """取出表达式的值，出错时返回 ``default``。"""
        e = QQmlExpression(self.engine.rootContext(), self.window, expr)
        value, _undefined = e.evaluate()
        return default if e.hasError() else value

    # ── 步骤 ────────────────────────────────────────────────
    def step_startup(self):
        check("启动时只显示主窗口", self.visible() == [MAIN_TITLE], f"{self.visible()}")
        self.eval_js("app.openSettings()")
        self.pump(600)
        check("设置窗口可打开", SETTINGS_TITLE in self.visible(), f"{self.visible()}")

        w = self.find(SETTINGS_TITLE)
        if w:
            w.close()
        self.pump(500)
        check("设置窗口关闭后隐藏", SETTINGS_TITLE not in self.visible(), f"{self.visible()}")

        err, msg = self.eval_js("app.openSettings()")
        check("关闭后仍能重新打开设置", not err, msg)
        self.pump(600)
        check("设置窗口重新可见", SETTINGS_TITLE in self.visible(), f"{self.visible()}")

        self.eval_js("app.openLogin()")
        self.pump(900)
        check("登录窗口可打开", LOGIN_TITLE in self.visible(), f"{self.visible()}")

        w = self.find(LOGIN_TITLE)
        if w:
            w.close()
        self.pump(500)
        check("登录窗口关闭后隐藏", LOGIN_TITLE not in self.visible(), f"{self.visible()}")

        err, msg = self.eval_js("app.openLogin()")
        check("关闭后仍能重新打开登录", not err, msg)
        self.pump(900)
        check("登录窗口重新可见", LOGIN_TITLE in self.visible(), f"{self.visible()}")

        # 关闭两个子窗口后应当只剩主窗口
        for needle in (SETTINGS_TITLE, LOGIN_TITLE):
            w = self.find(needle)
            if w:
                w.close()
        self.pump(500)
        check("子窗口关闭后只剩主窗口", self.visible() == [MAIN_TITLE], f"{self.visible()}")

        self.step_detail()

    # ── 歌单详情页 ──────────────────────────────────────────
    def step_detail(self):
        # 打开一个歌单详情（覆盖层是同步出现的，曲目在后台线程拉）
        self.eval_js("discover.openPlaylist('19723756', '测试歌单')")
        self.pump(1200)
        check("歌单详情覆盖层已打开", self.detail_open(),
              f"detailId={self.eval_value('discover.detailId')!r}")

        # 覆盖层不透明区域也不能点穿到底下的导航栏
        nav = self.window.findChild(QObject, "navPane")
        blocker = self.window.findChild(QObject, "playlistDetailBlocker")
        check("歌单详情遮罩存在", blocker is not None and nav is not None)
        if blocker is not None and nav is not None:
            # 导航第二项「搜索」（44px 一项，从 y=10 开始）
            point = self.to_point(nav, 60, 76)
            blocker.setProperty("enabled", False)
            self.click(point)
            self.pump(600)
            check("（对照）关掉歌单详情遮罩后确实会点穿",
                  self.eval_value("app.page", "") == "search",
                  f"page={self.eval_value('app.page')!r}")
            self.eval_js("app.go('discover')")

            blocker.setProperty("enabled", True)
            self.pump(300)
            self.click(point)
            self.pump(600)
            check("歌单详情覆盖层不穿透到底层页面",
                  self.eval_value("app.page", "") == "discover",
                  f"page={self.eval_value('app.page')!r}")

        button = self.window.findChild(QObject, "detailBackButton")
        check("找得到返回按钮", button is not None)
        if button is not None:
            # 真正触发按钮的 clicked 信号，验证它接到了 closePlaylist。
            # 这条链路断过一次：PlaylistDetailPanel 发了 closeRequested，
            # 但 Main.qml 里没有任何地方接收，点返回毫无反应。
            button.clicked.emit()
            self.pump(900)
            check("点返回后覆盖层关闭", not self.detail_open())

        self.step_now_playing()

    # ── 展开播放页 ──────────────────────────────────────────
    def step_now_playing(self):
        """展开播放页的三处缺陷：空白处点穿、隐藏歌词后封面不居中、歌词默认靠左。

        面板根节点只是普通 ``Item``，空白处不接收鼠标事件，展开后点空白会
        一路穿透到底下的导航栏；歌词靠左是写死的 ``Text.AlignLeft``；
        ``RowLayout`` 在歌词隐藏时只把封面留在左边。
        """
        self.eval_js("app.setExpanded(true)")
        self.pump(900)

        panel = self.window.findChild(QObject, "nowPlayingPanel")
        blocker = self.window.findChild(QObject, "nowPlayingBlocker")
        cover = self.window.findChild(QObject, "nowPlayingCoverColumn")
        nav = self.window.findChild(QObject, "navPane")
        check("展开播放页的面板 / 遮罩 / 封面列 / 导航都在",
              None not in (panel, blocker, cover, nav))
        if None in (panel, blocker, cover, nav):
            self.step_signal_params()
            return

        # 导航第二项「搜索」（44px 一项，从 y=10 开始）
        point = self.to_point(nav, 60, 76)

        # 负向对照：先关掉遮罩，证明这个点确实压在导航项上 —— 修复前就是这个行为
        blocker.setProperty("enabled", False)
        self.click(point)
        self.pump(600)
        check("（对照）关掉遮罩后确实会点穿到导航项",
              self.eval_value("app.page", "") == "search",
              f"page={self.eval_value('app.page')!r}")
        self.eval_js("app.go('discover')")

        blocker.setProperty("enabled", True)
        self.pump(300)
        self.click(point)
        self.pump(600)
        check("展开态点空白处不穿透到底层页面",
              self.eval_value("app.page", "") == "discover",
              f"page={self.eval_value('app.page')!r}")

        # 面板自己的控件不能被遮罩抢走事件
        collapse = self.window.findChild(QObject, "nowPlayingCollapseButton")
        if collapse is not None:
            self.click(self.to_point(collapse,
                                     collapse.property("width") / 2,
                                     collapse.property("height") / 2))
            self.pump(800)
            check("遮罩不会挡住面板上的按钮",
                  not self.eval_value("app.expanded", True))
            self.eval_js("app.setExpanded(true)")
            self.pump(700)

        # 隐藏歌词后封面区应当水平居中
        panel.setProperty("showLyrics", False)
        self.pump(700)
        offset = self.cover_offset(panel, cover)
        check("隐藏歌词后封面区居中", offset is not None and offset <= 1.0,
              f"偏差 {offset}px")
        panel.setProperty("showLyrics", True)
        self.pump(500)

        # 歌词对齐：默认居中，改设置立即生效
        check("歌词对齐默认为居中", self.settings.lyricAlignment == "center",
              f"{self.settings.lyricAlignment!r}")
        self.inject_lyrics()
        self.pump(600)
        centered = self.lyric_alignment(Qt.AlignHCenter)
        check("歌词行按居中渲染", centered is True,
              f"居中={centered} 靠左={self.lyric_alignment(Qt.AlignLeft)}")
        self.settings.set("lyrics.alignment", "left")
        self.pump(600)
        left = self.lyric_alignment(Qt.AlignLeft)
        check("设置里改成靠左立即生效", left is True,
              f"靠左={left} 居中={self.lyric_alignment(Qt.AlignHCenter)}")
        self.settings.set("lyrics.alignment", "center")
        self.pump(400)

        self.eval_js("app.setExpanded(false)")
        self.pump(600)

        self.step_signal_params()

    # ── 覆盖层 / 合成点击的辅助 ─────────────────────────────
    def to_point(self, item, x: float, y: float) -> QPoint:
        """把 item 内的坐标换算成窗口坐标（场景坐标与窗口坐标一致）。"""
        pt = item.mapToItem(None, QPointF(float(x), float(y)))
        return QPoint(round(pt.x()), round(pt.y()))

    def click(self, point: QPoint) -> None:
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, point, -1)

    def cover_offset(self, panel, cover) -> float | None:
        """封面列中心与面板中心的水平偏差（px）。"""
        x = cover.mapToItem(None, QPointF(0, 0)).x()
        center = x + float(cover.property("width")) / 2
        try:
            return abs(center - float(panel.property("width")) / 2)
        except (TypeError, ValueError):
            return None

    def inject_lyrics(self) -> None:
        """塞几行歌词，让歌词列表真的有 delegate 可以检查。"""
        from app.core.lyrics import Lyrics

        lyrics = Lyrics()
        lyrics.parse("[00:01.00]第一句测试歌词\n[00:11.00]第二句测试歌词\n[00:21.00]第三句测试歌词")
        self.player._lyrics = lyrics
        self.player._lyric_index = 1
        self.player.lyricChanged.emit()
        self.player.lyricIndexChanged.emit()

    def lyric_alignment(self, expected) -> bool | None:
        """第一条歌词行的水平对齐是否等于 expected；没有渲染出来时返回 None。

        比对放在 QML 表达式里做：``horizontalAlignment`` 是
        ``QQuickText::HAlignment``，从 Python 读会报
        ``Can't find converter``。
        """
        view = self.window.findChild(QObject, "lyricView")
        if view is None:
            return None
        content = view.property("contentItem")
        for row in (content.childItems() if content is not None else []):
            for text in row.childItems():
                if not str(text.property("text") or ""):
                    continue
                expr = QQmlExpression(self.engine.rootContext(), text,
                                      f"horizontalAlignment === {int(expected)}")
                value, _ = expr.evaluate()
                return None if expr.hasError() else bool(value)
        return None

    # ── 信号处理器参数 ──────────────────────────────────────
    def step_signal_params(self):
        """触发几个带参数的信号，确认没有「参数未声明」的废弃警告。"""
        nav = self.window.findChild(QObject, "navPane")
        check("找得到导航栏", nav is not None)
        if nav is not None:
            nav.pageRequested.emit("search")
            self.pump(400)
            check("导航信号可用", self.eval_value("app.page", "") == "search",
                  f"page={self.eval_value('app.page')!r}")

        injected = [m for m in QT_MESSAGES if "is not declared" in m]
        check("无信号参数注入警告", not injected, f"{injected[:2]}")

        self.qt_app.quit()

    def detail_open(self) -> bool:
        """歌单详情面板是否处于打开状态。"""
        return bool(self.eval_value("discover.detailId !== ''", False))

    def _finish(self) -> int:
        errors = [w for w in sorted(set(self.warnings))
                  if "TypeError" in w or "is not defined" in w or "Unable to assign" in w]
        check("无 QML 运行时错误", not errors, f"{errors[:3]}")
        print(f"\nFAILED: {FAILS if FAILS else 'none'}", flush=True)
        return 1 if FAILS else 0


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}", flush=True)
    if not cond:
        FAILS.append(name)


def main() -> int:
    qInstallMessageHandler(_qt_message_handler)
    probe = UiProbe(sys.argv)
    code = probe.run()
    return probe._finish() or code


if __name__ == "__main__":
    sys.exit(main())
