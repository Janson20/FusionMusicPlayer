"""UI 冒烟测试：启动真实 QML 界面并校验窗口与导航行为。

覆盖几个曾经真实出现过的缺陷：
1. ``FluWindow`` 的基类 ``Component.onCompleted`` 会无条件 ``show()``，
   导致设置 / 登录窗口跟着主窗口一起弹出来；
2. ``FluWindow.closeDestory`` 默认为 true，关闭即析构，之后 QML 里的 id
   变成已释放对象，再次调用 ``showWindow()`` 会抛
   ``Cannot call method 'showWindow' of null``；
3. 歌单详情页左上角「返回」发出的 ``closeRequested`` 没有接到任何地方，
   点了没反应（``discover.detailId`` 一直是空不了）。

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

from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, qInstallMessageHandler  # noqa: E402
from PySide6.QtQml import QQmlExpression  # noqa: E402

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

        button = self.window.findChild(QObject, "detailBackButton")
        check("找得到返回按钮", button is not None)
        if button is not None:
            # 真正触发按钮的 clicked 信号，验证它接到了 closePlaylist。
            # 这条链路断过一次：PlaylistDetailPanel 发了 closeRequested，
            # 但 Main.qml 里没有任何地方接收，点返回毫无反应。
            button.clicked.emit()
            self.pump(900)
            check("点返回后覆盖层关闭", not self.detail_open())

        self.step_signal_params()

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
