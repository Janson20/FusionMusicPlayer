import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
// 带命名空间导入：QtQuick.Controls 里也有 Menu / MenuItem，不限定会撞名
import Qt.labs.platform as Platform
import FluentUI
import "components"
import "pages"
import "panels"
import "windows"

/*!
    主窗口。

    结构完全对应设计草图：
        ┌──────────────────────────────────────────┐
        │ ◈ Fusion Music Player   [设置] − □ ✕      │  标题栏（含设置按钮）
        ├─────────┬────────────────────────────────┤
        │ 标签页   │            主界面               │
        ├─────────┴────────────────────────────────┤
        │ (封面)      ⏮ ▶ ⏭                    ^   │  底部播放栏
        └──────────────────────────────────────────┘
*/
FluWindow {
    id: root

    // 尺寸不用属性绑定：FluWindow 的无边框助手会在派生组件的绑定生效前后
    // 把窗口收敛到 minimumWidth/minimumHeight，绑定值会被吞掉。
    // 统一在 Component.onCompleted 里显式设置一次最可靠。
    //
    // 但**下限必须绑上**：低分辨率下（1366×768 被任务栏吃掉一截，或者开了 125%
    // 缩放）窗口若还按 940×620 起步，底部播放栏会被顶到屏幕外面、点都点不到。
    // 所以初始尺寸与最小尺寸都交给 app 按屏幕可用区域算（见 bridges/app.py）。
    width: app.initialWidth()
    height: app.initialHeight()
    minimumWidth: app.minimumWidth()
    minimumHeight: app.minimumHeight()
    title: "Fusion Music Player"
    visible: true
    autoMaximize: app.restoreMaximized()
    windowIcon: ""

    // 窗口背景：主题底色 + 可选的自定义背景图（设置 → 外观 → 背景图）。
    // FluWindow 的 background 是个 Component，会被它内部的 FluLoader 铺满整个窗口，
    // 这正是替换背景的入口（见 components/AppBackground.qml）。
    background: Component {
        AppBackground { }
    }

    // 缩到托盘时提示过一次就不再提示（每次关闭都弹气泡很烦）
    property bool trayHintShown: false

    // ── 标题栏（含草图里的「设置按钮」）──────────────────
    appBar: AppTitleBar {
        onSettingsClicked: root.openSettings()
    }

    // ── 主题色板（FluTheme.primaryColor 取 themeColor.dark）──
    FluColorSet {
        id: accentSet
        darkest: "#3A1D8F"
        darker: "#4C27B8"
        dark: "#6C4DF6"
        normal: "#7C5CFF"
        light: "#9B82FF"
        lighter: "#BCA9FF"
        lightest: "#DED5FF"
    }

    function applyAccent(hex) {
        var c = Qt.color(hex)
        accentSet.darkest = Qt.darker(c, 2.0)
        accentSet.darker = Qt.darker(c, 1.55)
        accentSet.dark = c
        accentSet.normal = Qt.lighter(c, 1.12)
        accentSet.light = Qt.lighter(c, 1.3)
        accentSet.lighter = Qt.lighter(c, 1.5)
        accentSet.lightest = Qt.lighter(c, 1.78)
        FluTheme.themeColor = accentSet
        Theme.accent = c
    }

    function applyTheme() {
        var mode = settings.theme
        if (mode === "dark")
            FluTheme.darkMode = FluThemeType.Dark
        else if (mode === "light")
            FluTheme.darkMode = FluThemeType.Light
        else
            FluTheme.darkMode = app.systemDark ? FluThemeType.Dark : FluThemeType.Light

        Theme.animations = settings.animations
        applyAccent(settings.accent)
    }

    Component.onCompleted: {
        if (!root.autoMaximize) {
            var w = app.initialWidth()
            var h = app.initialHeight()
            if (root.width !== w || root.height !== h) {
                root.width = w
                root.height = h
            }
            root.moveWindowToDesktopCenter()
        }
        applyTheme()
    }

    Connections {
        target: settings
        function onChanged() { root.applyTheme() }
    }
    Connections {
        target: app
        function onSystemDarkChanged() {
            if (settings.theme === "auto")
                root.applyTheme()
        }
    }

    // 通知
    Connections {
        target: app
        function onNotify(level, message) {
            if (level === "success")
                root.showSuccess(message, 2200)
            else if (level === "warning")
                root.showWarning(message, 2600)
            else if (level === "error")
                root.showError(message, 3200)
            else
                root.showInfo(message, 1800)
        }
        function onLoginRequested() { root.openLogin() }
        function onSettingsRequested() { root.openSettings() }
    }

    // ── 主内容区 ────────────────────────────────────────
    Item {
        anchors.fill: parent

        Item {
            id: mainArea
            anchors {
                top: parent.top
                left: parent.left
                right: parent.right
                bottom: playerBar.top
            }

            NavPane {
                id: nav
                objectName: "navPane"
                anchors {
                    top: parent.top
                    left: parent.left
                    bottom: parent.bottom
                }
                currentPage: app.page
                expanded: settings.navExpanded
                favoriteCount: library.favoritesModel.count
                historyCount: library.historyModel.count
                localCount: library.localModel.count
                downloadCount: download.activeCount
                onPageRequested: function (pageId) { app.go(pageId) }
                onLoginRequested: function () { root.openLogin() }
            }

            StackLayout {
                id: pageStack
                anchors {
                    top: parent.top
                    left: nav.right
                    right: parent.right
                    bottom: parent.bottom
                }
                currentIndex: {
                    switch (app.page) {
                    case "roam": return 1
                    case "search": return 2
                    case "library": return 3
                    case "local": return 4
                    case "queue": return 5
                    case "downloads": return 6
                    default: return 0
                    }
                }

                // 页面按需加载：列表里只有当前页（以及访问过的页）是活的。
                // 启动时全部实例化实测要多花约 0.3 秒（见 components/LazyPage.qml）
                LazyPage {
                    current: pageStack.currentIndex === 0
                    source: "pages/DiscoverPage.qml"
                }
                LazyPage {
                    current: pageStack.currentIndex === 1
                    source: "pages/RoamPage.qml"
                }
                LazyPage {
                    current: pageStack.currentIndex === 2
                    source: "pages/SearchPage.qml"
                }
                LazyPage {
                    current: pageStack.currentIndex === 3
                    source: "pages/LibraryPage.qml"
                }
                LazyPage {
                    current: pageStack.currentIndex === 4
                    source: "pages/LocalPage.qml"
                }
                LazyPage {
                    current: pageStack.currentIndex === 5
                    source: "pages/QueuePage.qml"
                }
                LazyPage {
                    current: pageStack.currentIndex === 6
                    source: "pages/DownloadsPage.qml"
                }
            }

            // 歌单详情覆盖层（从发现页打开）
            PlaylistDetailPanel {
                id: playlistDetail
                // 不要用 anchors.fill + x：两者冲突，滑入动画会被锚点吃掉。
                // 显式给宽高，x 才能正常参与动画。
                width: parent.width
                height: parent.height
                visible: discover.detailId !== ""
                x: visible ? 0 : width
                opacity: visible ? 1 : 0
                Behavior on x { NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
                // 左上角「返回」发出的是 closeRequested —— 之前没接上，点了没反应
                onCloseRequested: discover.closePlaylist()
            }

            // 专辑详情覆盖层（点任意地方的专辑名打开）
            //
            // 层级用**打开顺序**而不是声明顺序：专辑页与歌手页可以互相跳，
            // 谁后开谁在上面。声明顺序是固定的，只按它排的话，从歌手页点专辑名会
            // 打开一个被歌手页盖住的专辑页（看不见，还以为没反应）。
            AlbumDetailPanel {
                id: albumDetail
                z: album.layer
                width: parent.width
                height: parent.height
                visible: album.opened
                x: visible ? 0 : width
                opacity: visible ? 1 : 0
                Behavior on x { NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
                onCloseRequested: album.close()
            }

            // 歌手详情覆盖层（点任意地方的歌手名打开）
            ArtistDetailPanel {
                id: artistDetail
                z: artist.layer
                width: parent.width
                height: parent.height
                visible: artist.opened
                x: visible ? 0 : width
                opacity: visible ? 1 : 0
                Behavior on x { NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
                onCloseRequested: artist.close()
            }
        }

        // ── 底部播放栏（横跨整个窗口宽度）──────────────
        PlayerBar {
            id: playerBar
            anchors {
                left: parent.left
                right: parent.right
                bottom: parent.bottom
            }
            height: Theme.playerBarHeight
            expanded: app.expanded
            onExpandToggled: app.toggleExpanded()
            onOpenNowPlaying: app.setExpanded(true)
        }

        // ── 展开播放页 ──────────────────────────────────
        NowPlayingPanel {
            id: nowPlaying
            // 同上：不用 anchors.fill，否则 y 动画失效
            width: parent.width
            height: parent.height
            visible: opacity > 0
            opacity: app.expanded ? 1 : 0
            y: app.expanded ? 0 : height * 0.06
            onCollapseRequested: app.setExpanded(false)

            Behavior on opacity { NumberAnimation { duration: Theme.durationNormal } }
            Behavior on y { NumberAnimation { duration: Theme.durationSlow; easing.type: Easing.OutCubic } }
        }
    }

    // ── 系统托盘 ────────────────────────────────────────
    //
    // 用 Qt.labs.platform 的 SystemTrayIcon，而不是 QtWidgets 的 QSystemTrayIcon：
    // 后者的上下文菜单只吃 QMenu，而 QMenu 是 QWidget，得把整个程序从
    // QGuiApplication 换成 QApplication。这里问的是同一套平台接口（available 与
    // QSystemTrayIcon::isSystemTrayAvailable 结论一致），菜单还是系统原生菜单 ——
    // 主窗口藏进托盘之后照样弹得出来（QML 自己的 Menu 是画在窗口里的，
    // 窗口一藏就没地方画了）。
    Platform.SystemTrayIcon {
        id: tray
        objectName: "trayIcon"
        visible: app.trayUsable
        icon.source: app.trayIconSource
        tooltip: player.title !== ""
            ? player.title + (player.artist !== "" ? " - " + player.artist : "")
            : app.appName

        onActivated: function (reason) {
            // 左键单击 / 双击都回窗口；右键由系统弹 menu
            if (reason === Platform.SystemTrayIcon.Trigger
                    || reason === Platform.SystemTrayIcon.DoubleClick)
                root.restoreFromTray()
        }

        menu: Platform.Menu {
            objectName: "trayMenu"
            Platform.MenuItem {
                objectName: "trayMenuShow"
                text: "显示主窗口"
                onTriggered: root.restoreFromTray()
            }
            Platform.MenuSeparator { }
            Platform.MenuItem {
                objectName: "trayMenuToggle"
                text: player.playing ? "暂停" : "播放"
                enabled: player.title !== ""
                onTriggered: player.toggle()
            }
            Platform.MenuItem {
                objectName: "trayMenuPrev"
                text: "上一首"
                enabled: player.queueCount > 0
                onTriggered: player.previous()
            }
            Platform.MenuItem {
                objectName: "trayMenuNext"
                text: "下一首"
                enabled: player.queueCount > 0
                onTriggered: player.next()
            }
            Platform.MenuSeparator { }
            Platform.MenuItem {
                objectName: "trayMenuQuit"
                text: "退出"
                onTriggered: root.quitApp()
            }
        }
    }

    // ── 窗口状态持久化 ──────────────────────────────────
    //
    // 关闭窗口时存尺寸 / 最大化。**藏到托盘时不能存** —— 那一刻 visibility 是
    // Hidden，存下去会把用户上次调好的尺寸覆盖掉（见 saveWindowState）。
    closeListener: function (event) {
        root.handleClose(event)
    }

    // 关闭请求的唯一入口：标题栏的 ✕ / Alt+F4 走 closeListener，
    // 询问框选完走 applyCloseChoice，两边都从这里分派。
    // 返回真正执行的动作（tray / ask / quit），冒烟测试直接调它。
    function handleClose(event) {
        root.saveWindowState()
        var action = app.closeDecision()
        if (action === "tray") {
            if (event)
                event.accepted = false
            root.hideToTray()
            return action
        }
        if (action === "ask") {
            if (event)
                event.accepted = false
            closeDialog.remember = false
            closeDialog.open()
            return action
        }
        // 直接退出。窗口还开着时 destoryOnClose() 也管用，但退出统一走 quitApp()：
        // 两条路各用一套机制的话，「关窗退出」和「托盘退出」的可靠性会不一样
        root.quitApp()
        return action
    }

    function saveWindowState() {
        if (root.visibility === Window.Windowed || root.visibility === Window.Maximized) {
            if (root.visibility === Window.Windowed)
                app.saveWindowSize(root.width, root.height)
            app.saveMaximized(root.visibility === Window.Maximized)
        }
        app.flush()
    }

    // 最小化到托盘：窗口 hide() 掉（不是关掉），子窗口一起收走，
    // 否则「主窗口进了托盘、设置窗口还杵在桌面上」很怪
    function hideToTray() {
        root.closeAuxWindows()
        root.hide()
        if (!root.trayHintShown && tray.supportsMessages) {
            root.trayHintShown = true
            tray.showMessage(app.appName, "已最小化到托盘，播放不会中断",
                             Platform.SystemTrayIcon.Information, 3000)
        }
    }

    function restoreFromTray() {
        if (!root.visible)
            root.show()
        if (root.visibility === Window.Minimized)
            root.showNormal()
        root.raise()
        root.requestActivate()
    }

    // 退出程序：主窗口可能是藏着的，closeListener 不会跑，所以这里得自己把
    // 窗口状态存一次。
    //
    // **不要用 Qt.quit()** —— 托盘图标露过面之后它就失效了（Qt 有意让有托盘的
    // 程序不因窗口关闭而退出），点了「退出程序」会毫无反应，用户再点 ✕ 又弹一次
    // 询问框，看着像死循环。走 Python 侧的 exit(0)（见 app.quitApplication）。
    //
    // 退出前**先把界面收掉**：拆引擎（媒体后端、整棵 QML 对象树、托盘图标）要花
    // 一秒上下，窗口留在屏幕上就会显示成「未响应」（实测：留着窗口 2.6 秒才消失，
    // 先收窗口则窗口当场不见、进程随后无声退出）。改动前那版是 destoryOnClose()，
    // 窗口当场销毁，所以看着是「秒退」—— 这里补回同样的观感。
    function quitApp() {
        root.saveWindowState()
        root.closeAuxWindows()
        root.hide()
        tray.visible = false
        app.quitApplication()
    }

    // 询问框里选了什么。勾了「记住我的选择」就把它写进设置（设置页里能改回来）
    function applyCloseChoice(choice) {
        if (closeDialog.remember)
            app.setCloseAction(choice)
        // 先让弹窗自己关掉，再动窗口：quit 时带着一个开着的 popup 拆引擎，
        // 能不出事但没必要冒这个险
        closeDialog.close()
        Qt.callLater(function () {
            if (choice === "tray")
                root.hideToTray()
            else
                root.quitApp()
        })
    }

    // ── 快捷键 ──────────────────────────────────────────
    function isTyping() {
        var item = root.activeFocusItem
        if (!item)
            return false
        var name = "" + item
        return name.indexOf("TextField") >= 0
            || name.indexOf("TextInput") >= 0
            || name.indexOf("TextArea") >= 0
            || name.indexOf("TextEdit") >= 0
            || name.indexOf("SpinBox") >= 0
    }

    Shortcut {
        sequences: ["Space"]
        enabled: !root.isTyping()
        onActivated: player.toggle()
    }
    Shortcut { sequence: "Ctrl+Right"; enabled: !root.isTyping(); onActivated: player.next() }
    Shortcut { sequence: "Ctrl+Left"; enabled: !root.isTyping(); onActivated: player.previous() }
    Shortcut {
        sequence: "Ctrl+Up"
        onActivated: player.setVolume(Math.min(100, player.volume + 5))
    }
    Shortcut {
        sequence: "Ctrl+Down"
        onActivated: player.setVolume(Math.max(0, player.volume - 5))
    }
    Shortcut { sequence: "Ctrl+F"; onActivated: app.go("search") }
    Shortcut {
        sequence: "Escape"
        onActivated: {
            if (app.expanded) {
                app.setExpanded(false)
                return
            }
            // 关**最上面那层**：专辑与歌手可以互相跳，压在上面的是后开的那个
            // （layer 更大）。照固定顺序关的话，Esc 会去关一个被盖住的页面，
            // 界面上看起来就像没反应。
            if (artist.opened && (!album.opened || artist.layer > album.layer))
                artist.close()
            else if (album.opened)
                album.close()
            else if (discover.detailId !== "")
                discover.closePlaylist()
        }
    }

    // ── 惰性窗口（设置 / 登录）────────────────────────────
    //
    // SettingsWindow.qml 有 1100 行、LoginWindow.qml 400 行，之前是在这里直接
    // 实例化的：启动时多花约 0.3 秒编译一整棵从来不显示的对象树（两个窗口的
    // 根都是 visible: false）。改成第一次真要用时才建 —— 绝大多数启动根本用不到。
    //
    // 不能用 Loader：Loader 只装 Item，而 Window 不是 Item。这里走 Qt.createComponent。
    property var settingsWindow: null
    property var loginWindow: null

    function ensureWindow(existing, url) {
        if (existing)
            return existing
        var component = Qt.createComponent(Qt.resolvedUrl(url))
        if (component.status !== Component.Ready) {
            console.error("窗口创建失败 " + url + "：" + component.errorString())
            return null
        }
        return component.createObject(root)
    }

    function openSettings() {
        settingsWindow = ensureWindow(settingsWindow, "windows/SettingsWindow.qml")
        if (settingsWindow)
            settingsWindow.showWindow()
    }

    function openLogin() {
        loginWindow = ensureWindow(loginWindow, "windows/LoginWindow.qml")
        if (loginWindow)
            loginWindow.showWindow()
    }

    // 藏到托盘 / 退出前收子窗口：没建过的就别建了（否则退出时反而多花一笔）
    function closeAuxWindows() {
        if (settingsWindow)
            settingsWindow.hide()
        if (loginWindow)
            loginWindow.hide()
    }

    // ── 关闭主窗口的询问框 ──────────────────────────────
    FluContentDialog {
        id: closeDialog
        objectName: "closeDialog"
        // 「记住我的选择」勾没勾（每次打开都会重置，见 closeListener）
        property bool remember: false

        title: "关闭 " + app.appName
        message: "要让它在系统托盘里继续播放，还是退出程序？"
        buttonFlags: FluContentDialogType.NeutralButton
            | FluContentDialogType.NegativeButton
            | FluContentDialogType.PositiveButton
        neutralText: "最小化到托盘"
        negativeText: "取消"
        positiveText: "退出程序"

        contentDelegate: Component {
            Item {
                implicitHeight: 42
                FluCheckBox {
                    objectName: "closeRememberBox"
                    anchors.left: parent.left
                    anchors.leftMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    text: "记住我的选择（可在设置里改回来）"
                    checked: closeDialog.remember
                    clickListener: function () {
                        closeDialog.remember = !closeDialog.remember
                    }
                }
            }
        }

        onNeutralClicked: root.applyCloseChoice("tray")
        onPositiveClicked: root.applyCloseChoice("quit")
    }
}
