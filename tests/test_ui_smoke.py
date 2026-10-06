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
   点到底下的导航栏，隐藏歌词后封面区赖在左边，歌词写死靠左；
5. 展开播放页的「百科」标签页：切过去歌词还盖在原地、切回来回不去，以及
   没打开百科页就去联网取数（每切一首歌白跑三个请求）；
6. 本地音乐页：添加文件夹退回成「手输路径」的输入框（要的是系统选择器）；
7. 歌手页（``panels/ArtistDetailPanel.qml``）：点歌手名进不去、或者点歌手名
   顺带把整行点播了（整行的 MouseArea 压在歌手名链接上面）；
8. 专辑页（``panels/AlbumDetailPanel.qml``）：同上，另外专辑页必须盖在歌单页
   之上、歌手页必须盖在专辑页之上，否则点进去是个看不见的页面；
9. 恢复上次播放（``core/session.py`` + ``PlayerEngine``）：恢复出来的曲目只是
   摆在播放栏上、媒体还没交给 ``QMediaPlayer``，这时按播放不能是空操作；进度
   要接着上次走（``setPosition()`` 在媒体就绪前会被后端静默丢掉）；
10. 托盘与关闭策略（``Main.qml`` 的 ``SystemTrayIcon`` + ``bridges/app.py``）：
    关闭事件没被 ``event.accepted = false`` 拦下来（点了 ✕ 窗口直接销毁、进程也退）、
    托盘用不了却把窗口藏了起来（用户再也找不回程序）、询问框里勾的
    「记住我的选择」没写进设置；以及最后一步 —— 点「退出程序」必须**真的**退出
    （``Qt.quit()`` 在托盘图标露过面之后会被吞掉，用户再点 ✕ 又弹一次询问框，
    看着就是死循环，所以这里用 ``exit(0)``，并由 ``aboutToQuit`` 认领）。
11. 逐字歌词（``panels/NowPlayingPanel.qml`` + ``core/lyrics.py``）：有逐字数据却
    还按整行高亮（属性接上了但界面没用上）、关掉开关之后还在动。
12. 封面保存（``components/CoverSaveDialog.qml`` + ``core/covers.py``）：右键菜单
    弹不出来、另存为的默认名字不对、扩展名不按文件头纠正、失败时静默。
13. 音频缓存（``core/cache.py``）：按**播放地址**当键导致同一首歌存好几份
    （地址里嵌着时间戳），以及设置里那个「清理重复文件」按钮点了没反应。

无显示环境（CI）下需要一个虚拟屏幕::

    xvfb-run -a python tests/test_ui_smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 用独立的数据目录，避免污染真实配置
os.environ["FUSION_MUSIC_HOME"] = tempfile.mkdtemp(prefix="fusion_uitest_")

from PySide6.QtCore import (  # noqa: E402
    Q_ARG,
    QEventLoop,
    QMetaObject,
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


def _is_empty_url(value) -> bool:
    """QML 里 ``source`` 这类 URL 属性为空时是``QUrl('')``，字符串化并不等于空串。"""
    if value is None:
        return True
    empty = getattr(value, "isEmpty", None)
    if callable(empty):
        return bool(empty())
    return str(value) in ("", "undefined")


def _write_test_png(path: Path, width: int = 64, height: int = 48) -> Path:
    """写一张最小 PNG 当背景图素材（纯标准库，不额外依赖 Pillow）。"""
    import struct
    import zlib

    raw = b"".join(b"\x00" + bytes((200, 60, 60)) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    return path


class UiProbe(Application):
    def run(self) -> int:
        from app import paths

        self.warnings: list[str] = []
        # 最后一步要验「应用真的退出了」，靠 aboutToQuit 认；见 step_quit / _finish
        self.expect_quit = False
        self.quit_seen = False
        self.qt_app.aboutToQuit.connect(self._on_about_to_quit)
        self.engine.warnings.connect(self._on_warn)
        self.engine.load(QUrl.fromLocalFile(str(paths.qml_dir() / "Main.qml")))
        roots = self.engine.rootObjects()
        if not roots:
            check("QML 加载", False, "rootObjects 为空")
            return self._finish()
        check("QML 加载", True)
        self.window = roots[0]

        QTimer.singleShot(1200, lambda: self.guard(self.step_startup))
        self.exit_code = self.qt_app.exec()
        return self.exit_code

    # ── 工具 ────────────────────────────────────────────────
    def _on_warn(self, ws):
        self.warnings.extend(w.toString() for w in ws)

    def _on_about_to_quit(self) -> None:
        self.quit_seen = True

    def pump(self, ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def guard(self, step, *args) -> None:
        """跑一个步骤；步骤里漏出来的异常记成一条失败，而不是让测试卡死。

        这些步骤都是从 QTimer 回调里串起来的：回调里抛异常时事件循环再也不会
        退出，表现是「跑到一半不动了」，比失败还难查（PySide6 也只是把回溯
        打到 stderr）。所以每个步骤都从这里进。
        """
        try:
            step(*args)
        except Exception as e:
            check(f"{getattr(step, '__name__', step)} 跑得完（未抛异常）", False,
                  f"{type(e).__name__}: {e}")
            traceback.print_exc()

    def wait_until(self, predicate, timeout_ms: int = 8000, step: int = 200) -> bool:
        """等某个条件成立（后台线程的结果要等事件循环转起来）。"""
        spent = 0
        while spent < timeout_ms:
            if predicate():
                return True
            self.pump(step)
            spent += step
        return bool(predicate())

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

    # ── 背景图（设置 → 外观）──────────────────────────────────
    def check_background_section(self):
        """自定义背景图：入库 → 生效 → 旋钮真的作用到背景层 → 清除后回到纯色。

        这里守的是「设置项接上了但没有真的生效」这类毛病：光看设置里存了值不够，
        要能看见背景层拿到图、Effect 的 opacity 跟着滑块走、面板真的变半透明。
        """
        win = self.find(SETTINGS_TITLE)
        if win is None:
            check("背景图分区可检查", False, "设置窗口不在")
            return
        win.setProperty("section", 0)   # 外观
        self.pump(500)

        # 设置窗口是**另一个 QQuickWindow**，它的控件不在主窗口的项树里，
        # 必须从它自己的 contentItem 往下找
        root = win.property("contentItem")
        check("背景图有「选择图片」按钮",
              self.find_items("backgroundPickButton", root) != [])
        check("背景图有「恢复纯色背景」按钮",
              self.find_items("backgroundClearButton", root) != [])
        for name in ("backgroundOpacitySlider", "backgroundBlurSlider",
                     "backgroundScrimSlider", "surfaceSidebarSlider",
                     "surfaceBottomSlider", "surfaceOverlaySlider", "surfaceCardSlider"):
            check(f"背景图的 {name} 在位", self.find_items(name, root) != [])

        src = Path(tempfile.mkdtemp(prefix="fusion_bgimg_")) / "wallpaper.png"
        _write_test_png(src)
        self.settings.applyBackgroundImage(src.as_uri())
        self.pump(1200)

        check("应用背景图后设置生效", bool(self.settings.backgroundActive))
        image = self.item("appBackgroundImage")
        check("背景层拿到了图片",
              image is not None and not _is_empty_url(image.property("source")),
              repr(image.property("source")) if image is not None else "背景层不存在")

        bar = self.item("playerBar")
        check("底部播放栏半透明（比主体实，但要看得到图）",
              bar is not None and 0 < int(bar.property("color").alpha()) < 255,
              f"alpha={bar.property('color').alpha() if bar is not None else None}")

        # 歌词页（展开播放）也要能看到图，但**不能**透出底下的页面内容：
        # 它自带一份背景层（BackgroundLayer）+ 按分区参数压的主题色
        self.eval_js("app.setExpanded(true)")
        self.pump(1400)
        backdrop = self.item("nowPlayingBackdrop")
        check("歌词页自带背景层（底 + 图）",
              self.item("backgroundBase") is not None
              and self.item("appBackgroundImage") is not None)
        check("歌词页按分区参数压色（不是全实底）",
              backdrop is not None and 0 < float(backdrop.property("opacity")) < 1.0,
              f"opacity={backdrop.property('opacity') if backdrop is not None else None}")
        self.settings.setInt("appearance.surface_overlay", 25)
        self.pump(500)
        backdrop = self.item("nowPlayingBackdrop")
        check("歌词页的不透明度跟着分区滑块走",
              backdrop is not None and abs(float(backdrop.property("opacity")) - 0.25) < 0.02,
              f"opacity={backdrop.property('opacity') if backdrop is not None else None}")
        self.settings.setInt("appearance.surface_overlay", 62)
        self.eval_js("app.setExpanded(false)")
        self.pump(700)

        self.settings.setInt("appearance.background_opacity", 20)
        self.pump(400)
        effect = self.item("appBackgroundEffect")
        check("透明度滑块的值存进了设置", int(self.settings.backgroundOpacity) == 20,
              str(self.settings.backgroundOpacity))
        check("透明度真的作用到背景层",
              effect is not None and abs(float(effect.property("opacity")) - 0.2) < 0.02,
              f"opacity={effect.property('opacity') if effect is not None else None}")

        self.settings.clearBackgroundImage()
        self.pump(700)
        check("清除后设置回到纯色", not bool(self.settings.backgroundActive))
        image = self.item("appBackgroundImage")
        check("清除后背景层不再有图",
              image is None or _is_empty_url(image.property("source")),
              repr(image.property("source")) if image is not None else "背景层不存在")
        bar = self.item("playerBar")
        check("清除后面板恢复实色",
              bar is not None and int(bar.property("color").alpha()) == 255,
              f"alpha={bar.property('color').alpha() if bar is not None else None}")

    # ── 步骤 ────────────────────────────────────────────────
    def step_startup(self):
        check("启动时只显示主窗口", self.visible() == [MAIN_TITLE], f"{self.visible()}")
        self.eval_js("app.openSettings()")
        self.pump(600)
        check("设置窗口可打开", SETTINGS_TITLE in self.visible(), f"{self.visible()}")

        self.check_account_section()
        self.check_background_section()

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

        self.guard(self.step_detail)

    # ── 账号分区（凭据存储 / 便携模式）────────────────────────
    def check_account_section(self):
        """设置页的账号分区要能算出「密钥在本机解得开吗」。

        这里守的是一类很容易犯、又很难在别处暴露的错：``app/security`` 的
        ``__init__.py`` 把 ``vault`` 导成了**单例实例**，所以
        ``vault.dpapi_available()`` 这种「模块级函数当方法调」会在 QML 求值
        ``account.portableHint`` 时抛 AttributeError —— 界面那边只会报一行
        QML 运行时错误，靠 ``_finish()`` 那条检查才拦得住。
        """
        win = self.find(SETTINGS_TITLE)
        if win is None:
            check("账号分区可检查", False, "设置窗口不在")
            return
        win.setProperty("section", 3)
        self.pump(500)

        hint = self.eval_value("account.portableHint", None)
        check("便携模式说明能算出来", isinstance(hint, str) and hint != "", repr(hint))
        check("密钥可用性问得出来",
              self.eval_value("account.keyUsable", None) is not None)
        check("能问出当前平台有没有 DPAPI",
              self.eval_value("account.dpapiAvailable", None) is not None)

        switch = win.findChild(QObject, "portableModeSwitch")
        check("账号分区有便携模式开关", switch is not None)
        if switch is not None:
            check("开关跟着实际状态",
                  bool(switch.property("checked")) == bool(self.account.portableMode),
                  f"checked={switch.property('checked')} "
                  f"portableMode={self.account.portableMode}")

        card = win.findChild(QObject, "keyProblemCard")
        check("账号分区有「密钥解不开」提示卡片", card is not None)
        if card is not None:
            # 这条只在真的解不开时才显形（正常机器上不显示）
            check("密钥可用时提示卡片是隐藏的",
                  bool(card.property("visible")) != bool(self.account.keyUsable),
                  f"visible={card.property('visible')} keyUsable={self.account.keyUsable}")

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
            # 导航第二项（44px 一项，从 y=10 开始）—— 别写死是哪个页面，
            # 导航项以后可能插新的（漫游就是这么插进来的）
            point = self.to_point(nav, 60, 76)
            second_page = self.nav_page_at(1)
            blocker.setProperty("enabled", False)
            self.click(point)
            self.pump(600)
            check("（对照）关掉歌单详情遮罩后确实会点穿",
                  self.eval_value("app.page", "") == second_page,
                  f"page={self.eval_value('app.page')!r} 期望={second_page!r}")
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

        self.guard(self.step_now_playing)

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
            self.guard(self.step_signal_params)
            return

        # 导航第二项（44px 一项，从 y=10 开始）
        point = self.to_point(nav, 60, 76)
        second_page = self.nav_page_at(1)

        # 负向对照：先关掉遮罩，证明这个点确实压在导航项上 —— 修复前就是这个行为
        blocker.setProperty("enabled", False)
        self.click(point)
        self.pump(600)
        check("（对照）关掉遮罩后确实会点穿到导航项",
              self.eval_value("app.page", "") == second_page,
              f"page={self.eval_value('app.page')!r} 期望={second_page!r}")
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

        self.guard(self.step_karaoke)
        self.guard(self.step_cover_save)
        self.guard(self.step_song_wiki, panel)

        self.eval_js("app.setExpanded(false)")
        self.pump(600)

        self.guard(self.step_artist)

    # ── 逐字（动态）歌词 ────────────────────────────────────
    def step_karaoke(self):
        """逐字歌词：有逐字数据时按进度着色，关掉开关 / 没有数据就回到整行高亮。

        要守住的是「接上了但没有真的生效」这类毛病：光有 ``lyricProgress`` 属性
        不算数 —— 界面上必须能看见**已唱的字**被染成强调色、颜色边界随进度移动，
        而关掉开关之后必须回到原来的样子（否则「设置里关掉了还在动」）。
        """
        from app.core.lyrics import Lyrics

        lyrics = Lyrics()
        lyrics.parse("[00:01.00]第一句测试歌词\n[00:11.00]第二句测试歌词\n")
        lyrics.apply_pseudo()
        self.player._lyrics = lyrics
        self.player._lyric_index = 0
        self.player._lyric_progress = 0.0
        self.player.lyricChanged.emit()
        self.player.lyricIndexChanged.emit()
        self.player.lyricProgressChanged.emit()
        self.pump(600)

        accent = str(self.settings.accent).lower().lstrip("#")
        active = self.active_lyric_text()
        check("逐字歌词行渲染出来了", active is not None)
        if active is None:
            return
        styled, markup = self.lyric_markup(active)
        check("有逐字数据的当前行走富文本着色", styled is True, f"markup={markup[:60]!r}")
        check("进度为 0 时还没有字被点亮", accent not in markup.lower(),
              f"markup={markup[:60]!r}")

        # 唱到第 2.5 个字：前两个字应当是强调色，第三个字在过渡中
        self.player._lyric_progress = 2.5
        self.player.lyricProgressChanged.emit()
        self.pump(400)
        styled, markup = self.lyric_markup(active)
        check("进度推进后有字被点亮", accent in markup.lower(), f"markup={markup[:80]!r}")
        check("已唱的字包在强调色标签里",
              f'<font color="#{accent}">第一</font>' in markup.lower(),
              f"markup={markup[:80]!r}")

        # 一行唱完：整行都是强调色
        self.player._lyric_progress = float(len(lyrics.lines[0].text))
        self.player.lyricProgressChanged.emit()
        self.pump(400)
        _styled, markup = self.lyric_markup(active)
        check("整行唱完后不再有未唱色",
              markup.lower().count("<font") == 1, f"markup={markup[:80]!r}")

        # 关掉开关 → 回到纯文本（原来的整行高亮）
        self.settings.setBool("lyrics.dynamic", False)
        self.pump(400)
        styled, markup = self.lyric_markup(active)
        check("关掉逐字开关后是纯文本", styled is False and "<font" not in markup,
              f"styled={styled} markup={markup[:60]!r}")
        self.settings.setBool("lyrics.dynamic", True)
        self.pump(300)

        # 没有逐字数据的行（比如本地 .lrc 又没匹配上在线身份）保持整行高亮
        plain = Lyrics()
        plain.parse("[00:01.00]没有逐字数据的行\n[00:11.00]第二行\n")
        self.player._lyrics = plain
        self.player._lyric_index = 0
        self.player._lyric_progress = 0.0
        self.player.lyricChanged.emit()
        self.player.lyricIndexChanged.emit()
        self.pump(500)
        active = self.active_lyric_text()
        styled, markup = self.lyric_markup(active)
        check("没有逐字数据的行不做着色", styled is False and "<font" not in markup,
              f"styled={styled} markup={markup[:60]!r}")

        # 设置页里的开关真的在（配置项写了但界面没入口，等于没这个功能）
        win = self.find(SETTINGS_TITLE)
        if win is not None:
            previous = win.property("section")
            win.setProperty("section", 4)      # 歌词
            self.pump(500)
            switch = win.findChild(QObject, "lyricDynamicSwitch")
            check("设置 → 歌词里有逐字歌词开关", switch is not None)
            check("开关状态跟着配置走",
                  switch is not None and bool(switch.property("checked")) is True)
            win.setProperty("section", previous if previous is not None else 0)
            self.pump(300)

    # ── 封面保存 ────────────────────────────────────────────
    def step_cover_save(self):
        """封面保存：右键入口、另存为的默认值、真的落一个文件出来。

        封面来源用本地 ``file://``（等价于本地曲目内嵌封面那条路），
        不联网也能把「取封面 → 纠正扩展名 → 原子落盘 → 弹通知」整条链走完。
        """
        from pathlib import Path
        import tempfile

        panel = self.window.findChild(QObject, "nowPlayingPanel")
        area = self.window.findChild(QObject, "nowPlayingCoverArea")
        menu = self.window.findChild(QObject, "nowPlayingCoverMenu")
        save_item = self.window.findChild(QObject, "nowPlayingSaveCoverItem")
        check("展开播放页封面有右键区 / 菜单 / 保存项",
              None not in (area, menu, save_item))
        if None in (area, menu, save_item):
            return
        check("保存项的文字是「保存封面…」",
              str(save_item.property("text")) == "保存封面…",
              f"{save_item.property('text')!r}")

        # 右键真能弹出菜单（MouseArea 只吃右键，左键留给别的交互）
        self.right_click(self.to_point(area, area.property("width") / 2,
                                       area.property("height") / 2))
        self.pump(500)
        check("封面右键弹出菜单", bool(menu.property("visible")))
        menu.setProperty("visible", False)
        self.pump(300)

        tmp = Path(tempfile.mkdtemp(prefix="fusion_smoke_cover_"))
        png = _write_test_png(tmp / "embedded.png")
        track = {
            "name": "探针曲目", "singer": "探针歌手", "source": "local",
            "cover": QUrl.fromLocalFile(str(png)).toString(),
        }
        hint = self.app.coverSaveHint(track)
        hint = dict(hint) if isinstance(hint, dict) else {}
        check("另存为默认文件名是「歌手 - 歌名」",
              hint.get("name") == "探针歌手 - 探针曲目.png", f"{hint.get('name')!r}")
        check("另存为给了 file:// 的默认目录与文件",
              str(hint.get("folder", "")).startswith("file:")
              and str(hint.get("file", "")).startswith("file:"),
              f"{hint}")

        # 对话框自己的准备逻辑（不 open()：系统原生对话框是模态阻塞的，点不了）。
        # 用 invokeMethod 直接传参，**不能**把曲目拼进 QQmlExpression 的表达式字符串 ——
        # 那样中文会变成 "?"（实测「探针歌手 - 探针曲目」进到对话框里成了 "????.jpg"）。
        dialog = self.window.findChild(QObject, "coverSaveDialog")
        check("另存为对话框组件在", dialog is not None)
        if dialog is not None:
            prepared = QMetaObject.invokeMethod(
                dialog, "prepare", Qt.ConnectionType.DirectConnection, Q_ARG("QVariant", track)
            )
            check("对话框能按曲目准备好默认值", bool(prepared))
            current = dialog.property("currentFile")
            current_text = current.toString() if current is not None else ""
            check("默认文件名与扩展名进了对话框",
                  "探针歌手 - 探针曲目.png" in current_text
                  and current_text.startswith("file:"),
                  f"{current_text!r}")
            check("对话框默认扩展名跟着封面格式走",
                  str(dialog.property("defaultSuffix")) == "png",
                  f"{dialog.property('defaultSuffix')!r}")

        messages: list[str] = []
        self.app.notify.connect(lambda level, message: messages.append(f"{level}:{message}"))

        # ① 正常保存：目标扩展名故意写错（存的是 PNG，名字给 .jpg）
        dest = tmp / "out" / "手打名字.jpg"
        self.app.saveCover(track, QUrl.fromLocalFile(str(dest)).toString())
        fixed = dest.with_suffix(".png")
        saved = self.wait_until(lambda: fixed.exists(), timeout_ms=8000)
        check("封面真的落到磁盘上", saved, f"{list((tmp / 'out').glob('*')) if (tmp / 'out').exists() else '目录都没建'}")
        check("扩展名按文件头纠正成 .png",
              saved and not dest.exists(), f"{dest.name} / {fixed.name}")
        check("落盘的字节与源封面一致",
              saved and fixed.read_bytes() == png.read_bytes())
        check("落盘后没有任何 *.part 残渣",
              not list((tmp / "out").glob("*.part")))
        self.wait_until(lambda: any("封面已保存" in m for m in messages), timeout_ms=4000)
        check("保存成功有通知", any("封面已保存" in m for m in messages), f"{messages}")

        # ② 没有封面可存：给的是能读懂的中文失败提示，而不是静默失败
        messages.clear()
        self.app.saveCover({"name": "没有封面的本地曲", "source": "local"},
                           QUrl.fromLocalFile(str(tmp / "nothing.jpg")).toString())
        self.wait_until(lambda: bool(messages), timeout_ms=8000)
        check("没有封面时给出失败提示",
              any("保存封面失败" in m for m in messages), f"{messages}")
        check("失败时不会凭空造出文件", not (tmp / "nothing.jpg").exists())

        panel.setProperty("showLyrics", True)
        self.pump(200)

    # ── 歌曲百科标签页 ──────────────────────────────────────
    def step_song_wiki(self, panel):
        """百科标签页：切得过去、切得回来、切过去才去取数。

        真实数据来自网易云的百科区块页（``netease.song_wiki``），这里塞两行假的
        —— 冒烟测试不联网。要守住的是三件曾经很容易做错的事：标签页点了没反应、
        切到百科后歌词还留在原地盖着、以及**没打开百科页就去联网取数**
        （每切一首歌白跑三个请求）。
        """
        tabs = self.find_items("nowPlayingTab")
        check("右侧卡片上有「歌词 / 百科」两个标签", len(tabs) == 2, f"{len(tabs)} 个")

        self.inject_wiki_rows()
        panel.setProperty("tab", 1)
        self.pump(700)

        lyric_view = self.window.findChild(QObject, "lyricView")
        pane = self.window.findChild(QObject, "songWikiPane")
        check("百科面板在切过去后显示", pane is not None and pane.isVisible())
        check("切到百科后歌词让位", lyric_view is not None and not lyric_view.isVisible())

        rows = self.find_items("songWikiRow")
        check("百科面板按行渲染出来", len(rows) == 2, f"{len(rows)} 行")
        # find_items 是栈式遍历，行的顺序不保证，拼起来一起看
        texts = [t for row in rows for t in self.row_texts(row)]
        check("百科行有标签和值",
              all(t in texts for t in ("曲风", "探针曲风", "BPM", "120")), f"{texts}")

        # 面板没展开时不该去取数（这里是「停在百科但收起了卡片」）
        check("百科标签下 wikiActive 为真", panel.property("wikiActive") is True)
        panel.setProperty("showLyrics", False)
        self.pump(400)
        check("收起卡片后不再取数", panel.property("wikiActive") is False)
        panel.setProperty("showLyrics", True)
        self.pump(400)
        check("重新展开后又开始取数", panel.property("wikiActive") is True)

        panel.setProperty("tab", 0)
        self.pump(500)
        check("切回歌词标签后歌词回来",
              lyric_view is not None and lyric_view.isVisible())
        check("切回歌词后百科面板让位", pane is not None and not pane.isVisible())
        check("切回歌词后不再取数", panel.property("wikiActive") is False)

    # ── 歌手页 ──────────────────────────────────────────────
    def step_artist(self):
        """歌手页：点歌手名进得去、点行内其它位置仍然播放、搜索置顶卡片接得上。

        曲目与置顶卡片都用注入的数据，不依赖联网 —— 真实接口由音源层的
        ``netease.artist_page`` 负责，冒烟测试只盯界面接线。
        """
        self.eval_js("app.go('search')")
        self.pump(600)
        self.inject_search_rows()
        self.pump(700)

        row = self.top_row()
        check("搜索列表渲染出曲目行", row is not None)
        if row is None:
            self.guard(self.step_signal_params)
            return

        # 行里的歌手名：进歌手页，且不会顺带把歌播了
        links = self.find_items("trackRowArtistLink", row)
        # 「A、B」必须渲染成**两个**可点的名字。拆不开时整串会变成一个链接，
        # 点下去找的是「A、B」这个不存在的歌手（真机上弹「没找到歌手」）；
        # 拆得开的前提是扫描时把标签归一化过（见 test_core 的歌手拆分用例）。
        check("两个歌手渲染成两个可点的名字", len(links) == 2, f"{len(links)} 个")

        # 中间那个「 / 」必须是**独立**的一项：塞进歌手名的文本里的话，悬停时
        # 下划线会把它一起划上、点击区域也把它算进去，看着像名字的一部分。
        seps = self.find_items("trackRowArtistSep", row)
        check("歌手之间的分隔符是独立的一项", len(seps) == 1, f"{len(seps)} 个")
        check("歌手名里不带分隔符",
              all("/" not in str(t.property("text")) for t in links),
              f"{[t.property('text') for t in links]}")

        # 悬停第二位歌手：只有它自己高亮，分隔符不能跟着变
        ordered = sorted(links, key=lambda i: i.mapToItem(None, QPointF(0, 0)).x())
        if len(ordered) == 2 and seps:
            target = ordered[1]
            QTest.mouseMove(self.window, self.to_point(
                target, target.property("width") / 2, target.property("height") / 2))
            self.pump(400)
            check("悬停歌手名时它自己高亮", self.text_underline(target) is True)
            check("悬停时分隔符不跟着高亮", self.text_underline(seps[0]) is False)

        playing_before = self.current_track()
        if links:
            self.click_item(links[0])
            check("点歌手名打开歌手页", self.artist.opened)
            check("点歌手名不会顺带播放", self.current_track() == playing_before,
                  f"{playing_before!r} -> {self.current_track()!r}")

        back = self.item("artistBackButton")
        check("歌手页找得到返回按钮", back is not None)
        if back is not None:
            self.click_item(back)
            self.pump(700)
            check("点返回关闭歌手页", not self.artist.opened)

        # 行内其它位置仍然是「播放整行」
        row = self.top_row()
        if row is not None:
            self.click_scene(row, 120, 26)
            self.pump(1200)
            check("点行内其它位置仍然是播放",
                  self.current_track() == "测试歌曲 A", f"{self.current_track()!r}")
            check("点行内其它位置不会打开歌手页", not self.artist.opened)

        # 搜索置顶卡片
        self.inject_tops()
        self.pump(800)
        card = self.item("searchTopArtistCard")
        check("置顶歌手卡片渲染出来了",
              card is not None and float(card.property("height")) > 40,
              f"h={card.property('height') if card is not None else None}")
        check("置顶卡片没有把结果列表挤掉", self.top_row() is not None)
        if card is not None:
            self.click_item(card)
            check("点置顶卡片打开歌手页",
                  self.artist.opened and self.artist.pageId == "33699297",
                  f"id={self.artist.pageId!r}")
            self.artist.close()
            self.pump(500)

        # 展开播放页里的歌手名：先收起展开页，再进歌手页
        self.eval_js("app.setExpanded(true)")
        self.pump(900)
        np_links = self.find_items("nowPlayingArtistLink")
        check("展开播放页里的歌手名可以点", len(np_links) > 0)
        if np_links:
            self.click_item(np_links[0])
            check("点展开页的歌手名会先收起展开页",
                  not self.eval_value("app.expanded", True))
            check("展开页点歌手名也能进歌手页", self.artist.opened)
            self.artist.close()
            self.pump(500)
            self.eval_js("app.setExpanded(false)")
            self.pump(500)

        # 找不到的歌手（跨音源常见）：不能卡在加载中
        self.artist.openByName("zzz 不存在的歌手 zzz")
        check("点不存在的歌手时面板先开着",
              self.artist.opened and self.artist.loading)
        settled = self.wait_until(lambda: not self.artist.loading, 10000)
        check("找不到歌手时不会卡在加载中",
              settled and not self.artist.opened,
              f"loading={self.artist.loading} opened={self.artist.opened}")

        self.search.clear()
        self.pump(400)

        self.guard(self.step_album)

    # ── 专辑页 ──────────────────────────────────────────────
    def step_album(self):
        """专辑页：点专辑名进得去、行内其它位置仍然播放、展开页与播放栏也能进。

        和歌手页一样用注入数据，不依赖联网。
        """
        self.eval_js("app.go('search')")
        self.pump(500)
        self.inject_search_rows()
        self.pump(700)

        row = self.top_row()
        check("搜索列表渲染出曲目行（专辑页用）", row is not None)
        if row is None:
            self.guard(self.step_signal_params)
            return

        album_links = self.find_items("trackRowAlbumLink", row)
        check("曲目行里的专辑名可以点", len(album_links) > 0, f"{len(album_links)} 个")
        # 专辑名前面那个「 · 」必须是**独立**的一项，不能拼进专辑名里
        # （拼进去的话悬停时下划线会把它一起划上，和歌手名之间那个斜杠一个毛病）
        for link in album_links:
            check("专辑名里不带分隔符",
                  "·" not in str(link.property("text")),
                  repr(link.property("text")))
        if album_links:
            check("专辑名前面有独立的分隔符",
                  len(self.find_items("trackRowAlbumSep", row)) == 1,
                  f"{len(self.find_items('trackRowAlbumSep', row))} 个")
        playing_before = self.current_track()
        if album_links:
            self.click_item(album_links[0])
            check("点专辑名打开专辑页", self.album.opened)
            check("点专辑名不会顺带播放", self.current_track() == playing_before,
                  f"{playing_before!r} -> {self.current_track()!r}")

        back = self.item("albumBackButton")
        check("专辑页找得到返回按钮", back is not None)
        if back is not None:
            self.click_item(back)
            self.pump(700)
            check("点返回关闭专辑页", not self.album.opened)

        # 行内其它位置仍然是「播放整行」
        row = self.top_row()
        if row is not None:
            self.click_scene(row, 120, 26)
            self.pump(1200)
            check("点行内其它位置仍然是播放（专辑）",
                  self.current_track() == "测试歌曲 A", f"{self.current_track()!r}")
            check("点行内其它位置不会打开专辑页", not self.album.opened)

        # 播放栏的歌手名：和曲目行、展开播放页必须是同一套渲染。
        # 曾经这里把整串歌手名塞进一个 Text ——「WOVOP、洛天依」看着像**一个**
        # 名字（别处是「 / 」分开的），点下去还只进第一位。
        bar_links = [i for i in self.find_items("playerBarArtistLink") if i.isVisible()]
        bar_seps = [i for i in self.find_items("playerBarArtistSep") if i.isVisible()]
        check("播放栏两个歌手渲染成两个可点的名字", len(bar_links) == 2, f"{len(bar_links)} 个")
        check("播放栏歌手之间的分隔符是独立的一项", len(bar_seps) == 1, f"{len(bar_seps)} 个")
        check("播放栏歌手名里不带分隔符",
              all("、" not in str(t.property("text")) for t in bar_links),
              f"{[t.property('text') for t in bar_links]}")
        if len(bar_links) == 2:
            ordered = sorted(bar_links, key=lambda i: i.mapToItem(None, QPointF(0, 0)).x())
            check("播放栏歌手按原顺序排列",
                  [str(t.property("text")) for t in ordered] == ["WOVOP", "洛天依"],
                  f"{[t.property('text') for t in ordered]}")
            self.click_item(ordered[1])
            check("点播放栏歌手打开歌手页", self.artist.opened)
            check("点播放栏第二位歌手进的就是第二位",
                  "洛天依" in str(self.artist.pageTitle), str(self.artist.pageTitle))
            back = self.item("artistBackButton")
            if back is not None:
                self.click_item(back)
                self.pump(600)

        # 播放栏的专辑名
        bar_album = self.item("playerBarAlbumLink")
        check("播放栏里的专辑名可以点", bar_album is not None)
        if bar_album is not None:
            # 和曲目行同一个毛病：分隔符不能拼进专辑名里
            check("播放栏的专辑名里不带分隔符",
                  "·" not in str(bar_album.property("text")),
                  repr(bar_album.property("text")))
            check("播放栏有独立的分隔符",
                  self.item("playerBarAlbumSep") is not None)
            self.click_item(bar_album)
            check("点播放栏专辑名打开专辑页", self.album.opened)
            self.album.close()
            self.pump(500)

        # 展开播放页的专辑名：先收起展开页，再进专辑页
        self.eval_js("app.setExpanded(true)")
        self.pump(900)
        np_album = self.item("nowPlayingAlbumLink")
        check("展开播放页里的专辑名可以点", np_album is not None)
        if np_album is not None:
            # 等展开动画结束、链接真的可见了再点，否则点到的是动画中途的位置
            self.wait_until(lambda: bool(np_album.isVisible()), 3000)
            self.click_item(np_album)
            check("点展开页的专辑名会先收起展开页",
                  not self.eval_value("app.expanded", True),
                  f"expanded={self.eval_value('app.expanded')}")
            check("展开页点专辑名也能进专辑页", self.album.opened,
                  f"album.opened={self.album.opened}")
            self.album.close()
            self.pump(500)
            self.eval_js("app.setExpanded(false)")
            self.pump(400)

        # 找不到的专辑：不能卡在加载中
        self.album.openByName("zzz 不存在的专辑 zzz")
        settled = self.wait_until(lambda: not self.album.loading, 10000)
        check("找不到专辑时不会卡在加载中",
              settled and not self.album.opened,
              f"loading={self.album.loading} opened={self.album.opened}")

        self.search.clear()
        self.pump(400)

        self.guard(self.step_overlay_stack)
        self.guard(self.step_roam)

    # ── 歌手页点专辑名：层级要按打开顺序 ────────────────────
    def step_overlay_stack(self):
        """从歌手页点专辑名，专辑页必须盖在歌手页**上面**。

        两个覆盖层原先按 QML 声明顺序排（歌手页声明在后面，于是永远压着专辑页），
        从歌手页点专辑名就打开了一个被盖住的页面 —— 看起来像「点了没反应」。
        现在每次打开领一个递增的 ``layer``，界面拿它当 ``z``。
        """
        self.inject_artist_page()
        self.pump(800)

        artist_panel = self.window.findChild(QObject, "artistDetailPanel")
        album_panel = self.window.findChild(QObject, "albumDetailPanel")
        check("歌手页与专辑页都在", None not in (artist_panel, album_panel))
        if None in (artist_panel, album_panel):
            return

        check("先打开的歌手页在最上面",
              artist_panel.property("z") > album_panel.property("z"),
              f"artist={artist_panel.property('z')} album={album_panel.property('z')}")

        # 只找歌手页**里面**的专辑名：别的页面在它后面，行也还在可视树里
        links = self.find_items("trackRowAlbumLink", artist_panel)
        check("歌手页里点得到专辑名", len(links) > 0, f"{len(links)} 个")
        if links:
            self.click_item(links[0])
            self.pump(700)
            check("从歌手页点专辑名能打开专辑页", self.album.opened)
            check("专辑页盖在歌手页上面",
                  album_panel.property("z") > artist_panel.property("z"),
                  f"artist={artist_panel.property('z')} album={album_panel.property('z')}")
            # 歌手页要留着：返回来才退得回去
            check("歌手页仍然开着（返回能退回来）", self.artist.opened)

        self.album.close()
        self.artist.close()
        self.pump(400)

    # ── 漫游 ────────────────────────────────────────────────
    def step_roam(self):
        """漫游页：推荐流渲染、开始漫游、听别的歌自动交棒。

        推荐流用注入的假数据（真接口要联网，而且每次都不一样）；续歌时机
        另由 ``tests/test_core.py::test_roam_refill_rules`` 离线覆盖。
        """
        # 先占住「已经取过」，免得页面切过去时自己去联网
        self.roam._requested = True
        self.inject_roam_stream()

        names = [str(item.get("name")) for item in self.nav_items()]
        check("导航栏里有「漫游」", "漫游" in names, f"{names}")

        self.eval_js("app.go('roam')")
        self.pump(800)
        row = self.top_row()
        check("漫游页渲染出推荐流", row is not None)
        if row is not None:
            check("推荐流显示推荐理由",
                  len(self.find_items("trackRowReason", row)) > 0)

        # 开始漫游：进队列 + 进入漫游态
        self.roam.playFrom(0)
        self.pump(600)
        check("开始漫游后处于漫游态", self.roam.active)
        check("漫游流进了播放队列",
              int(self.eval_value("player.queueCount", 0) or 0) == self.roam.count,
              f"queue={self.eval_value('player.queueCount')} roam={self.roam.count}")

        # 去听别的歌 → 漫游交棒，不再往队列里塞歌
        self.player.playTrack({"source": "wy", "songmid": "smoke-other",
                               "name": "别的歌", "singer": "别人", "interval": 120})
        self.pump(800)
        check("播放别的歌后漫游自动交棒", not self.roam.active)

        self.eval_js("app.go('discover')")
        self.pump(400)

        self.guard(self.step_local_page)

    # ── 本地音乐页 ──────────────────────────────────────────
    def step_local_page(self):
        """本地音乐页的文件夹要走**系统选择器**，不能又退回让人手输路径。

        以前这里是个「粘贴文件夹的完整路径」的输入框：容易打错，也没法浏览。
        换成 ``QtQuick.Dialogs`` 的 FolderDialog 之后，选出来的是 ``file://`` URL，
        得靠 Python 侧归一化（``library.normalize_folder``）—— 那一条由
        ``test_core.py`` 盯，这里只确认界面上挂的确实是系统选择器。
        """
        self.eval_js("app.go('local')")
        self.pump(700)

        dialog = self.window.findChild(QObject, "localFolderDialog")
        check("本地音乐页有文件夹选择器", dialog is not None)
        if dialog is not None:
            # 认能力不认类名：PySide 给 QQuickFolderDialog 报的 className() 是
            # "QFileDialogOptions"（它基类上的 options 对象），照类名判断会误判。
            # 真正的区分点是 selectedFolder —— InputDialog 没有这个属性。
            check("选择器是系统 FolderDialog 而不是输入框",
                  dialog.property("selectedFolder") is not None
                  and not hasattr(dialog, "openWith"),
                  f"{dialog.metaObject().className()}")
            # 标题来自我们自己的 QML，能确认挂上来的就是这一个
            check("选择器的标题来自本地音乐页",
                  str(dialog.property("title")) == "选择音乐文件夹",
                  repr(dialog.property("title")))

        check("扫描阶段属性可用", self.eval_value("library.scanPhase", None) is not None)

        self.eval_js("app.go('discover')")
        self.pump(300)

        self.guard(self.step_session_restore)

        self.guard(self.step_equalize)
        self.guard(self.step_cache_dedupe)
        self.guard(self.step_updater)
        self.guard(self.step_many_artists)

        self.guard(self.step_tray)

        self.guard(self.step_signal_params)

    # ── 音频缓存去重 ────────────────────────────────────────
    def step_cache_dedupe(self):
        """音频缓存去重：内容相同的只留一份，并且真的弹通知。

        背景：老版本按**播放地址**当缓存键，而地址里嵌着当前时间戳，同一首歌
        每次解析都不一样 —— 于是同一首歌被存好几份（实测用户盘上 140 个文件里
        44 组内容完全重复）。现在按曲目身份缓存（见 core/cache.py:media_identity），
        设置里的这个按钮用来收拾已经堆在盘上的旧账。
        """
        from app import paths

        win = self.find(SETTINGS_TITLE)
        if win is not None:
            win.setProperty("section", 6)   # 存储
            self.pump(500)
            check("设置 → 存储里有「清理重复文件」按钮",
                  win.findChild(QObject, "dedupeCacheButton") is not None,
                  "按钮不在（分区或对象名变了）")

        base = paths.media_cache_dir()
        base.mkdir(parents=True, exist_ok=True)
        payload = b"cache-bytes" * 512
        first = base / "smoke-dedupe-a.mp3"
        second = base / "smoke-dedupe-b.mp3"
        first.write_bytes(payload)
        second.write_bytes(payload)
        try:
            messages: list[str] = []
            self.settings.message.connect(lambda text: messages.append(str(text)))
            self.settings.dedupeCache()
            cleaned = self.wait_until(
                lambda: not (first.exists() and second.exists()), timeout_ms=10000
            )
            check("重复的缓存文件被删掉一份",
                  cleaned and (first.exists() or second.exists()),
                  f"a={first.exists()} b={second.exists()}")
            check("清理完给了通知",
                  any("重复" in m for m in messages), f"{messages}")
        finally:
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)

    # ── 音量均衡 ────────────────────────────────────────────
    def step_equalize(self):
        """音量均衡：音量滑块读的是**用户音量**，增益另算。

        守的是这一条：``QAudioOutput.volume()`` 上那个值是「用户音量 × 淡入淡出
        × 均衡增益」的乘积，滑块要是绑到它，播放中一分析出结果滑块就会自己跳。
        """
        import tempfile
        from pathlib import Path

        from app.core.loudness_store import Measurement
        from app.core.models import Track

        win = self.find(SETTINGS_TITLE)
        if win is None:
            check("均衡分区可检查", False, "设置窗口不在")
            return
        win.setProperty("section", 1)          # 播放分区
        self.pump(400)

        check("设置里有「启用音量均衡」开关",
              win.findChild(QObject, "equalizeSwitch") is not None)
        check("设置里有目标响度下拉",
              win.findChild(QObject, "targetLufsBox") is not None)

        stats = self.settings.loudnessStats
        check("响度统计可读",
              isinstance(stats, dict) and "measured" in stats and "pending" in stats,
              f"{stats}")

        # 拿一个本地静音 wav 当在播曲目（不联网），再塞一条测量值进去
        wav = Path(tempfile.mkdtemp(prefix="fusion_eq_")) / "eq.wav"
        write_silent_wav(wav, seconds=2)
        track = Track(source="local", songmid=str(wav), name="均衡测试", path=str(wav))

        old_current = self.player._current
        self.player._current = track
        self.eval_js("player.setVolume(80)")
        self.pump(150)
        before = self.player._output.volume()

        self.loudness.store.put(Measurement(
            uid=track.uid, loudness_lufs=-10.0, peak=1.0, seconds=180.0,
            partial=False, source="local", method="decode", ok=True))
        self.player._set_track_gain(track, ramp=False)
        after = self.player._output.volume()

        check("均衡增益改变了实际输出音量", after < before - 0.01,
              f"{before:.3f} -> {after:.3f}")
        check("音量滑块仍然是用户音量（80）", self.player.volume == 80,
              f"player.volume={self.player.volume}")
        check("增益说明能显示出来", "dB" in self.player.gainLabel,
              f"{self.player.gainLabel!r}")

        # 收尾：把状态还原，别影响后面的步骤
        self.loudness.store.remove(track.uid)
        self.player._current = old_current
        self.player._set_track_gain(old_current, ramp=False)

        self.settings.clearLoudness()
        self.pump(300)
        check("清空分析数据后统计归零", self.settings.loudnessStats["measured"] == 0,
              f"{self.settings.loudnessStats}")

    # ── 自动更新 ────────────────────────────────────────────
    def step_updater(self):
        """自动更新：不联网也要能显示状态；源码运行必须走「打开发布页」这条路。

        这里**不触发真的检查**（CI 与本地都不该依赖 GitHub 可达），只验证状态机
        与界面绑定；网络那一半由 ``tests/test_core.py`` 的纯函数用例覆盖。
        """
        check("更新控制器版本号与程序一致",
              self.updater.currentVersion == self.app.version,
              f"{self.updater.currentVersion} vs {self.app.version}")
        check("发行形态判定得出结果",
              self.updater.installKind in ("source", "onedir", "onefile"),
              self.updater.installKind)
        check("源码运行时不允许自动安装", self.updater.canInstall is False)
        check("并且给出了原因", bool(self.updater.installHint), self.updater.installHint)
        check("初始状态是 idle", self.updater.state == "idle", self.updater.state)
        check("发布页地址指向本仓库",
              "github.com/Janson20/FusionMusicPlayer" in self.updater.releaseUrl,
              self.updater.releaseUrl)

        win = self.find(SETTINGS_TITLE)
        if win is None:
            check("更新分区可检查", False, "设置窗口不在")
            return
        win.setProperty("section", 7)          # 关于分区
        self.pump(400)
        check("设置里有「检查更新」按钮",
              win.findChild(QObject, "checkUpdateButton") is not None)
        check("设置里有「自动检查更新」开关",
              win.findChild(QObject, "autoCheckUpdateSwitch") is not None)

        # 自动检查开关可写回配置（不联网）
        self.updater.setAutoCheck(False)
        check("关掉自动检查写进了配置", self.config.get("update.auto_check") is False)
        self.updater.setAutoCheck(True)
        check("再打开也写回去了", self.config.get("update.auto_check") is True)
        check("状态文案不抛异常", isinstance(self.updater.statusText, str),
              repr(self.updater.statusText))

    # ── 托盘与「关闭主窗口时」────────────────────────────────
    def step_tray(self):
        """托盘图标 + 关闭主窗口的三条路。

        离屏环境（以及某些 Linux 桌面）根本没有通知区域，所以先把
        ``app._tray_available`` 假装成 True —— 不然「收进托盘」这条路一次都走不到。
        这里守的是最要命的一种错法：托盘用不了还把窗口藏起来，用户点了 ✕
        就再也找不回程序（纯逻辑那一半在 test_core 的 test_close_decision 里）。
        """
        from app.bridges.app import close_decision

        # ── 托盘图标与菜单 ──────────────────────────────
        tray = self.window.findChild(QObject, "trayIcon")
        check("主窗口里有托盘图标", tray is not None)
        texts = self.tray_menu_texts()
        for want in ("显示主窗口", "上一首", "下一首", "退出"):
            check(f"托盘菜单有「{want}」", want in texts, f"{texts}")
        check("托盘菜单有播放 / 暂停", ("播放" in texts) or ("暂停" in texts), f"{texts}")
        # 提示文字应当是「歌名 - 歌手」，没在播就是应用名（此刻队列已被上一步清空）
        title = str(self.eval_value("player.title", "") or "")
        artist = str(self.eval_value("player.artist", "") or "")
        if title and artist:
            expected_tip = f"{title} - {artist}"
        else:
            expected_tip = title or MAIN_TITLE
        check("托盘悬停提示跟着在播曲目走",
              str(tray.property("tooltip") or "") == expected_tip,
              f"{tray.property('tooltip')!r} != {expected_tip!r}")
        # 图标显不显形要看环境：真机上一般是有托盘的，离屏环境里没有
        check("托盘图标跟着「系统支持 + 开关打开」走",
              bool(tray.property("visible")) == bool(self.eval_value("app.trayUsable", False)),
              f"visible={tray.property('visible')!r} "
              f"usable={self.eval_value('app.trayUsable')!r}")

        # ── 设置里的两项 ────────────────────────────────
        self.eval_js("app.openSettings()")
        self.pump(600)
        win = self.find(SETTINGS_TITLE)
        check("设置窗口开着（托盘与关闭策略在里面）", win is not None)
        if win is not None:
            win.setProperty("section", 0)
            self.pump(300)
            check("设置里有「显示托盘图标」开关",
                  win.findChild(QObject, "trayIconSwitch") is not None)
            check("设置里有「关闭主窗口时」下拉",
                  win.findChild(QObject, "closeActionBox") is not None)
            win.close()
            self.pump(400)

        # ── 假装系统有托盘 ──────────────────────────────
        # （真机上本来就是 True，这里统一成 True：离屏环境没有通知区域）
        had_tray = self.app._tray_available
        self.app._tray_available = True
        self.app.trayChanged.emit()
        self.pump(300)
        check("托盘可用后应用这边也认", bool(self.eval_value("app.trayUsable", False)))

        self.app.setCloseAction("tray")
        self.pump(200)
        check("策略跟着设置走（最小化到托盘）",
              self.eval_value("app.closeDecision()", "") == close_decision("tray", True),
              f"{self.eval_value('app.closeDecision()')!r}")

        # 真的走一次关窗事件（title 栏 ✕ / Alt+F4 那条路），而不是直接调内部函数：
        # 要验的正是「closeListener 里把 event.accepted 置回 false 拦下了关闭」
        self.window.close()
        self.pump(700)
        check("关闭被拦下：窗口是藏起来的，没被销毁",
              self.window_alive() and not self.window.isVisible(),
              f"alive={self.window_alive()} visible={self.window.isVisible()}")

        self.eval_js("restoreFromTray()")
        self.pump(600)
        check("能从托盘回到窗口", bool(self.window.isVisible()))

        # ── 询问框 + 记住我的选择 ───────────────────────
        self.app.setCloseAction("ask")
        self.pump(200)
        self.window.close()
        self.pump(600)

        dialog = self.window.findChild(QObject, "closeDialog")
        check("询问框弹了出来",
              dialog is not None and bool(dialog.property("visible")),
              f"{None if dialog is None else dialog.property('visible')}")
        check("询问期间窗口没被关掉", self.window_alive() and bool(self.window.isVisible()))
        if dialog is not None:
            check("询问框的两个出口是「最小化到托盘 / 退出程序」",
                  dialog.property("neutralText") == "最小化到托盘"
                  and dialog.property("positiveText") == "退出程序",
                  f"{dialog.property('neutralText')!r} / {dialog.property('positiveText')!r}")

        box = self.window.findChild(QObject, "closeRememberBox")
        check("询问框里有「记住我的选择」勾选框", box is not None)

        if dialog is not None and box is not None:
            dialog.setProperty("remember", True)
            self.pump(200)
            check("勾选框跟着 remember 走", bool(box.property("checked")))

            self.eval_js("applyCloseChoice('tray')")
            self.pump(800)
            check("勾了「记住」就把选择写进了设置",
                  self.app.closeAction == "tray", f"{self.app.closeAction!r}")
            check("选「最小化到托盘」后窗口收走", not self.window.isVisible())
            check("询问框自己关掉了", not bool(dialog.property("visible")))

            self.eval_js("restoreFromTray()")
            self.pump(500)

        # 收尾：策略与托盘可用性恢复原样，后面的步骤照旧
        self.app.setCloseAction("ask")
        self.app._tray_available = had_tray
        self.app.trayChanged.emit()
        self.pump(300)

    def window_alive(self) -> bool:
        """主窗口对象还在不在。

        ``destoryOnClose()`` 之后 QML 侧的 id 会变成已释放对象，再访问就抛
        RuntimeError —— 这正是「点了 ✕ 窗口直接没了」的样子。
        """
        try:
            return bool(self.window.property("title"))
        except RuntimeError:
            return False

    def tray_menu_texts(self) -> list[str]:
        """系统托盘菜单里各项的文字。

        按 objectName 一个个取，而不是读 ``tray.menu.items``：``menu`` 的类型是
        ``QQuickLabsPlatformMenu*``，Python 侧读它会抛
        ``Can't find converter for 'QQuickLabsPlatformMenu*'``（而菜单项本身
        是挂在窗口对象树上的，findChild 拿得到）。
        """
        out = []
        for name in ("trayMenuShow", "trayMenuToggle", "trayMenuPrev",
                     "trayMenuNext", "trayMenuQuit"):
            item = self.window.findChild(QObject, name)
            if item is not None:
                out.append(str(item.property("text") or ""))
        return out

    # ── 播放会话（启动时恢复上次的队列与在播曲目）────────────
    def step_session_restore(self):
        """会话恢复：队列与在播曲目摆回来，按播放键从上次的进度接着放。

        守的是两个很容易漏的分支：

        1. 恢复出来的曲目只是**摆在播放栏上**，媒体还没交给 ``QMediaPlayer``，
           这时 ``_player.play()`` 是空操作 —— 按播放键必须走一次正常加载；
        2. 恢复的进度只对恢复的那一首生效，别一按下一首也从头接着上次的秒数。

        曲目用的是**本地文件**（测试自己造的静音 wav）：解析不需要联网。
        """
        from app.core import session as play_session
        from app.core.models import Track
        from app.core.queue import PlayQueue

        wav = Path(tempfile.mkdtemp(prefix="fusion_session_audio_")) / "probe.wav"
        write_silent_wav(wav, seconds=3)

        queue = PlayQueue()
        queue.set_tracks([
            Track(source="local", name="会话曲目 A", path=str(wav), interval=3),
            Track(source="local", name="会话曲目 B", path=str(wav), interval=3),
        ], 1)
        check("会话写得进磁盘", play_session.save(queue, 1500) is True)

        check("恢复会话成功", self.player.restoreSession() is True)
        check("队列摆回来了", self.player.queueCount == 2, f"queueCount={self.player.queueCount}")
        check("当前曲目是上次那首", self.current_track() == "会话曲目 B",
              f"{self.current_track()!r}")
        check("进度接着上次", self.player.position == 1500, f"{self.player.position}")
        check("恢复出来不会自己出声", not self.player.playing and not self.player.paused)

        # 播放栏上的歌名是 QML 侧读 player.title 绑出来的，这里读的是真渲染值
        title = self.item("playerBarTitle")
        check("播放栏显示了恢复出来的歌名",
              title is not None and str(title.property("text") or "") == "会话曲目 B",
              f"{title.property('text') if title is not None else None!r}")

        # 按播放：媒体还没进来，必须真的走一次加载（否则点了没反应）
        self.player.toggle()
        check("按播放后开始加载", bool(self.player.loading), f"loading={self.player.loading}")
        self.pump(900)
        check("媒体确实交给了播放器", self.player._media_ready is True)

        # 退出时写得回去
        self.player.saveSession()
        again = play_session.load()
        check("退出时把会话写回去了",
              again is not None and len(again.tracks) == 2 and again.index == 1,
              f"{None if again is None else (len(again.tracks), again.index)}")

        self.player.clearQueue()

    # ── 覆盖层 / 合成点击的辅助 ─────────────────────────────
    def to_point(self, item, x: float, y: float) -> QPoint:
        """把 item 内的坐标换算成窗口坐标（场景坐标与窗口坐标一致）。"""
        pt = item.mapToItem(None, QPointF(float(x), float(y)))
        return QPoint(round(pt.x()), round(pt.y()))

    def click(self, point: QPoint) -> None:
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, point, -1)

    def right_click(self, point: QPoint) -> None:
        QTest.mouseClick(self.window, Qt.MouseButton.RightButton,
                         Qt.KeyboardModifier.NoModifier, point, -1)

    def active_lyric_text(self):
        """歌词列表里**当前高亮**那一行的文本项（``lyricMainText``）。"""
        index = self.player.lyricIndex
        texts = self.find_items("lyricMainText")
        texts.sort(key=lambda t: t.mapToItem(None, QPointF(0, 0)).y())
        if not texts:
            return None
        if 0 <= index < len(texts):
            return texts[index]
        return texts[0]

    def lyric_markup(self, item) -> tuple:
        """歌词文本项的 ``(是否富文本, 文本内容)``。

        两个坑：``textFormat`` 从 Python 侧读会报
        ``Can't find converter for 'QQuickText::TextFormat'``；而枚举名 ``Text``
        只能在**带 QtQuick 导入的那个上下文**里解析（用全局根上下文会报
        ``ReferenceError: Text is not defined``，探针
        ``tools/probe_text_format.py`` 里复现过）。所以两件事都在可视项自己的
        上下文里算。
        """
        if item is None:
            return (None, "")
        text = str(item.property("text") or "")
        fmt = self.qml_enum(item, "String(textFormat)")
        styled = self.qml_enum(item, "Text.StyledText")
        if fmt is None or styled is None:
            return (None, text)
        return (str(fmt) == str(styled), text)

    def qml_enum(self, scope_item, expression: str):
        """在 ``scope_item`` 自己的 QML 上下文里求值（枚举名要靠它解析）。"""
        context = None
        try:
            context = self.engine.contextForObject(scope_item)
        except Exception:
            context = None
        expr = QQmlExpression(context or self.engine.rootContext(), scope_item, expression)
        value, _undefined = expr.evaluate()
        return None if expr.hasError() else value

    def click_item(self, item) -> None:
        self.click(self.to_point(item, item.property("width") / 2,
                                 item.property("height") / 2))
        self.pump(400)

    def click_scene(self, item, x: float, y: float) -> None:
        self.click(self.to_point(item, x, y))

    def item(self, name: str, index: int = 0):
        found = self.find_items(name)
        return found[index] if len(found) > index else None

    def find_items(self, name: str, root=None) -> list:
        """按 objectName 找可视项。

        ``Repeater`` 动态创建出来的项（曲目行里的歌手名、展开播放页的歌手名）
        不在 QObject 子树上，``findChildren`` 找不到，只能走可视项树。
        """
        out: list = []
        stack = [root if root is not None else self.window.property("contentItem")]
        while stack:
            node = stack.pop()
            if node is None:
                continue
            if node.objectName() == name:
                out.append(node)
            children = getattr(node, "childItems", None)
            if children is not None:
                stack.extend(children())
        return out

    def top_row(self):
        """搜索页里最上面那一行曲目（在视口内，保证点得到）。"""
        rows = [r for r in self.find_items("trackRow") if r.isVisible()]
        rows.sort(key=lambda r: r.mapToItem(None, QPointF(0, 0)).y())
        return rows[0] if rows else None

    def current_track(self) -> str:
        return str(self.eval_value("player.currentTrack ? player.currentTrack.name : ''", "") or "")

    def nav_items(self) -> list:
        """导航项列表（``items`` 是 JS 数组，得先 toVariant 才拿得到 Python list）。"""
        nav = self.window.findChild(QObject, "navPane")
        if nav is None:
            return []
        value = nav.property("items")
        try:
            return list(value.toVariant() or [])
        except AttributeError:
            return list(value or [])

    def nav_page_at(self, index: int) -> str:
        """导航栏第 index 项对应的页面 id（顺序变了也不会误判）。"""
        items = self.nav_items()
        if 0 <= index < len(items):
            return str(items[index].get("id") or "")
        return ""

    def inject_search_rows(self) -> None:
        """塞两首假歌进搜索列表，免得冒烟测试依赖联网的搜索结果。"""
        from app.core.models import Track

        self.search._model.set_tracks([
            Track(source="wy", songmid="probe-1", name="测试歌曲 A",
                  singer="WOVOP、洛天依", album="探针专辑", interval=215),
            Track(source="wy", songmid="probe-2", name="测试歌曲 B",
                  singer="洛天依", album="探针专辑", interval=180),
        ])

    def inject_roam_stream(self) -> None:
        """塞一条假的漫游流（带推荐理由），不联网。"""
        from app.core.models import Track

        tracks = []
        for i in range(3):
            track = Track(source="wy", songmid=f"roam-{i}", name=f"漫游歌曲 {i}",
                          singer="探针歌手", album="探针专辑", interval=180 + i)
            track.reason = "你关注的音乐人新歌"
            tracks.append(track)
        self.roam._model.set_tracks(tracks)
        self.roam.changed.emit()

    def inject_tops(self) -> None:
        """注入搜索置顶卡片的数据（真实数据来自网易云搜索接口）。"""
        self.search._top_artist = {
            "id": "33699297", "name": "WOVOP", "cover": "", "alias": [],
            "music_size": 168, "album_size": 58, "mv_size": 8, "fans_size": 40894,
        }
        self.search._top_playlist = {
            "id": "12582973548", "name": "WOVOP", "cover": "",
            "track_count": 82, "play_count": 964, "creator": "香香软软的柚鸟夏",
        }
        self.search.topsChanged.emit()

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

    def inject_artist_page(self) -> None:
        """给歌手页灌一条数据，并让它领到**真实的**层级号。

        真接口要联网，这里直接填模型；``layer`` 必须走同一个计数器 —— 手写一个
        大数字会让「谁后开谁在上面」这件事失去意义（第一版探针就是这么把自己
        绕进去的）。
        """
        from app.bridges.detail import _layer_seq
        from app.core.models import Track

        self.artist._meta = {
            "id": "33699297", "name": "WOVOP", "cover": "", "alias": [],
            "brief_desc": "", "music_size": 1, "album_size": 1,
            "mv_size": 0, "fans_size": 0,
        }
        self.artist._model.set_tracks([
            Track(source="wy", songmid="smoke-artist-1", name="测试歌曲 A",
                  singer="WOVOP", album="探针专辑", album_id="33699298", interval=215),
        ])
        self.artist._opened = True
        self.artist._layer = next(_layer_seq)
        self.artist.changed.emit()

    def inject_wiki_rows(self) -> None:
        """塞两行假的百科（真数据来自网易云的百科区块页，冒烟测试不联网）。

        此刻播放器还没有当前曲目，``wiki`` 的「当前曲目 uid」是空串，所以这份
        注入不会在切换标签时被它的换歌判断清掉。
        """
        self.wiki._rows = [
            {"label": "曲风", "value": "探针曲风"},
            {"label": "BPM", "value": "120"},
        ]
        self.wiki.changed.emit()

    def row_texts(self, item) -> list[str]:
        """收集一个可视项子树里的所有 ``text``（百科行的标签与值）。"""
        out: list[str] = []
        stack = list(item.childItems()) if hasattr(item, "childItems") else []
        while stack:
            node = stack.pop()
            value = node.property("text")
            if isinstance(value, str) and value:
                out.append(value)
            children = getattr(node, "childItems", None)
            if children is not None:
                stack.extend(children())
        return out

    def text_underline(self, item) -> bool | None:
        """文本有没有下划线；读不到返回 None。

        走 QML 表达式：``font`` 是分组属性，从 Python 侧读会在转换上踩坑
        （和 :meth:`lyric_alignment` 里 ``horizontalAlignment`` 一样）。
        """
        expr = QQmlExpression(self.engine.rootContext(), item, "font.underline")
        value, _ = expr.evaluate()
        return None if expr.hasError() else bool(value)

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

    # ── 多歌手时的折叠（企划曲 / 周年纪念集）──────────────────
    def step_many_artists(self):
        """十几位歌手时，展开播放页那一行**不能溢出**。

        守的是用户报上来的显示问题：歌手行是按「名字 + 分隔符」逐个排的
        ``RowLayout``，它**不会换行** —— 名字多的时候整行会被撑到窗口两边，
        横着盖住封面、歌词和专辑名（真机截图里那一行从最左铺到了最右）。
        修法是只铺开前几位，其余折叠成「等 N 人」（点开是完整列表）。

        这里读的是**真实渲染出来的几何**：把每个歌手名映射到窗口坐标，
        看它们有没有跑出所属列的范围 —— 光断言「模型里有几项」是拦不住
        布局溢出的。
        """
        import tempfile
        from pathlib import Path

        from app.core.models import Track

        names = ["原幻乐社(十八渡)", "非凤FreakMalus", "莫临Moris", "伪证的火云龙",
                 "洛天依Official", "言和", "乐正绫", "墨清弦", "心华", "星尘",
                 "海伊", "赤羽", "苍穹", "诗岸", "乐正龙牙", "牧心", "微羽摩柯"]

        wav = Path(tempfile.mkdtemp(prefix="fusion_artists_")) / "many.wav"
        write_silent_wav(wav, seconds=2)
        track = Track(source="local", songmid=str(wav), name="一载梦尘录",
                      singer="、".join(names), album="幻乐社周年纪念作品集", path=str(wav))

        self.eval_js("app.setExpanded(true)")
        self.pump(600)
        self.player._current = track
        self.player.trackChanged.emit()
        self.pump(700)

        links = [i for i in self.find_items("nowPlayingArtistLink") if i.isVisible()]
        more = [i for i in self.find_items("nowPlayingArtistMore") if i.isVisible()]
        # 展开播放页那一栏只有 180~330px 宽，铺开 2 位正好：再多每位就只剩
        # 五十来像素，名字会被省略号啃得看不出是谁
        check("只铺开前 2 位歌手", len(links) == 2, f"links={len(links)}")
        check("其余折叠成「等 N 人」", len(more) == 1 and
              str(more[0].property("text")) == f"等 {len(names)} 人",
              f"{[i.property('text') for i in more]}")

        column = self.window.findChild(QObject, "nowPlayingCoverColumn")
        check("找得到封面列", column is not None)
        if column is not None and links and more:
            left = self.to_point(column, 0, 0).x()
            right = left + float(column.property("width"))
            items = links + more
            boxes = []
            for item in items:
                origin = self.to_point(item, 0, 0).x()
                boxes.append((origin, origin + float(item.property("width"))))
            spilled = [b for b in boxes if b[0] < left - 1 or b[1] > right + 1]
            check("歌手一行没有溢出所属列",
                  not spilled,
                  f"列=[{left:.0f},{right:.0f}] 歌手项={[(round(a), round(b)) for a, b in boxes]}")

        # 完整列表从「等 N 人」进去，一个都不能少（这里的 names 就是菜单的数据源）
        menu = self.window.findChild(QObject, "nowPlayingArtistMenu")
        raw_names = menu.property("names") if menu is not None else None
        if hasattr(raw_names, "toVariant"):     # property var 拿回来的是 QJSValue
            raw_names = raw_names.toVariant()
        check("「等 N 人」背后挂着完整歌手列表",
              menu is not None and len(raw_names or []) == len(names),
              f"{None if menu is None else len(raw_names or [])} / {len(names)}")

        # 列表行（TrackRow）用的是同一套规则，也要折叠 + 不溢出
        self.eval_js("app.go('search')")
        self.pump(600)
        self.search._model.set_tracks([
            Track(source="wy", songmid="many-artists", name="一载梦尘录",
                  singer="、".join(names), album="幻乐社周年纪念作品集", interval=310),
        ])
        self.pump(700)

        row = self.top_row()
        check("列表行渲染出来了", row is not None)
        if row is not None:
            row_links = [i for i in self.find_items("trackRowArtistLink", row) if i.isVisible()]
            row_more = [i for i in self.find_items("trackRowArtistMore", row) if i.isVisible()]
            check("列表行也只铺开前 3 位歌手", len(row_links) == 3, f"{len(row_links)} 个")
            check("列表行同样折叠出「等 N 人」",
                  len(row_more) == 1 and str(row_more[0].property("text"))
                  == f"等 {len(names)} 人",
                  f"{[i.property('text') for i in row_more]}")

            row_left = self.to_point(row, 0, 0).x()
            row_right = row_left + float(row.property("width"))
            boxes = []
            for item in row_links + row_more:
                origin = self.to_point(item, 0, 0).x()
                boxes.append((origin, origin + float(item.property("width"))))
            check("列表行的歌手没有跑出行外",
                  all(b[0] >= row_left - 1 and b[1] <= row_right + 1 for b in boxes),
                  f"行=[{row_left:.0f},{row_right:.0f}] 歌手项={[(round(a), round(b)) for a, b in boxes]}")

            albums = [i for i in self.find_items("trackRowAlbumLink", row) if i.isVisible()]
            if albums and boxes:
                album_left = self.to_point(albums[0], 0, 0).x()
                gap = album_left - max(b[1] for b in boxes)
                # 专辑名必须紧跟在歌手后面：只给子项 fillWidth 的话，多出来的
                # 宽度会被分给歌手名，专辑名被推到行尾（中间一段空白）
                check("专辑名紧跟在歌手后面（没被挤到行尾）", -2 <= gap <= 24,
                      f"间距={gap:.1f}px")

        # 收尾：还原当前曲目与页面，别影响后面的步骤
        self.player._current = None
        self.player.trackChanged.emit()
        self.eval_js("app.setExpanded(false)")
        self.eval_js("app.go('discover')")
        self.pump(400)

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

        self.guard(self.step_quit)

    # ── 退出程序 ────────────────────────────────────────────
    def step_quit(self):
        """最后一步：走「询问框 → 退出程序」，应用必须**真的**退出。

        守的正是用户报上来的那个死循环：托盘图标露过面之后 ``Qt.quit()`` 会被
        吞掉（Qt 有意让有托盘的程序不因窗口关闭而退出），点了「退出程序」毫无
        反应，用户再点 ✕ 又弹一次询问框。这里如果退不出去，watchdog 会兜住，
        由 ``_finish`` 报成失败，而不是让整个测试挂住。
        """
        self.app.setCloseAction("ask")
        self.app._tray_available = True
        self.app.trayChanged.emit()
        self.pump(300)

        self.window.close()              # 真关窗 → 询问框
        self.pump(700)
        dialog = self.window.findChild(QObject, "closeDialog")
        check("退出的询问框已经弹出来了",
              dialog is not None and bool(dialog.property("visible")),
              f"{None if dialog is None else dialog.property('visible')}")
        if dialog is not None:
            dialog.setProperty("remember", False)

        # 兜底：真卡住就 4 秒后强退，让 _finish 去报失败
        QTimer.singleShot(4000, lambda: self.qt_app.exit(99))
        self.expect_quit = True
        self.eval_js("applyCloseChoice('quit')")
        self.pump(2500)                  # 退出去的话，这里根本回不来

    def detail_open(self) -> bool:
        """歌单详情面板是否处于打开状态。"""
        return bool(self.eval_value("discover.detailId !== ''", False))

    def _finish(self) -> int:
        errors = [w for w in sorted(set(self.warnings))
                  if "TypeError" in w or "is not defined" in w or "Unable to assign" in w]
        check("无 QML 运行时错误", not errors, f"{errors[:3]}")
        if self.expect_quit:
            check("点「退出程序」之后应用真的退出了（aboutToQuit 到了）", self.quit_seen)
            # watchdog 是「退不出去」时的兜底，它也会触发 aboutToQuit ——
            # 不加这一条的话，真退不出去也会被上面那条判成通过
            check("退出不是被 watchdog 强退的", self.exit_code == 0,
                  f"exit_code={self.exit_code}")
        print(f"\nFAILED: {FAILS if FAILS else 'none'}", flush=True)
        return 1 if FAILS else 0


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}", flush=True)
    if not cond:
        FAILS.append(name)


def write_silent_wav(path: Path, seconds: float = 3.0, rate: int = 8000) -> None:
    """造一个能真播的静音 wav（恢复会话那一步拿它当本地曲目，不联网）。"""
    import wave

    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(1)
        f.setframerate(rate)
        f.writeframes(b"\x80" * int(rate * seconds))


def main() -> int:
    qInstallMessageHandler(_qt_message_handler)
    probe = UiProbe(sys.argv)
    code = probe.run()
    return probe._finish() or code


if __name__ == "__main__":
    sys.exit(main())
