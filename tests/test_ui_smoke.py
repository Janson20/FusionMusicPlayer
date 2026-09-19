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
6. 歌手页（``panels/ArtistDetailPanel.qml``）：点歌手名进不去、或者点歌手名
   顺带把整行点播了（整行的 MouseArea 压在歌手名链接上面）；
7. 专辑页（``panels/AlbumDetailPanel.qml``）：同上，另外专辑页必须盖在歌单页
   之上、歌手页必须盖在专辑页之上，否则点进去是个看不见的页面。

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

        self.step_song_wiki(panel)

        self.eval_js("app.setExpanded(false)")
        self.pump(600)

        self.step_artist()

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
            self.step_signal_params()
            return

        # 行里的歌手名：进歌手页，且不会顺带把歌播了
        links = self.find_items("trackRowArtistLink", row)
        check("曲目行里的歌手名可以点", len(links) > 0, f"{len(links)} 个")
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

        self.step_album()

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
            self.step_signal_params()
            return

        album_links = self.find_items("trackRowAlbumLink", row)
        check("曲目行里的专辑名可以点", len(album_links) > 0, f"{len(album_links)} 个")
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

        # 播放栏的专辑名
        bar_album = self.item("playerBarAlbumLink")
        check("播放栏里的专辑名可以点", bar_album is not None)
        if bar_album is not None:
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

        self.step_roam()

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

        self.step_signal_params()

    # ── 覆盖层 / 合成点击的辅助 ─────────────────────────────
    def to_point(self, item, x: float, y: float) -> QPoint:
        """把 item 内的坐标换算成窗口坐标（场景坐标与窗口坐标一致）。"""
        pt = item.mapToItem(None, QPointF(float(x), float(y)))
        return QPoint(round(pt.x()), round(pt.y()))

    def click(self, point: QPoint) -> None:
        QTest.mouseClick(self.window, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier, point, -1)

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
