import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
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
    width: 1180
    height: 760
    minimumWidth: 940
    minimumHeight: 620
    title: "Fusion Music Player"
    visible: true
    autoMaximize: app.restoreMaximized()
    windowIcon: ""

    // ── 标题栏（含草图里的「设置按钮」）──────────────────
    appBar: AppTitleBar {
        onSettingsClicked: settingsWindow.showWindow()
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
        function onLoginRequested() { loginWindow.showWindow() }
        function onSettingsRequested() { settingsWindow.showWindow() }
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
                onPageRequested: app.go(pageId)
                onLoginRequested: loginWindow.showWindow()
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
                    case "search": return 1
                    case "library": return 2
                    case "local": return 3
                    case "queue": return 4
                    default: return 0
                    }
                }

                DiscoverPage { }
                SearchPage { }
                LibraryPage { }
                LocalPage { }
                QueuePage { }
            }

            // 歌单详情覆盖层（从发现页打开）
            PlaylistDetailPanel {
                id: playlistDetail
                anchors.fill: parent
                visible: discover.detailId !== ""
                x: visible ? 0 : parent.width
                opacity: visible ? 1 : 0
                Behavior on x { NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutCubic } }
                Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
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
            anchors.fill: parent
            visible: opacity > 0
            opacity: app.expanded ? 1 : 0
            y: app.expanded ? 0 : parent.height * 0.06
            onCollapseRequested: app.setExpanded(false)

            Behavior on opacity { NumberAnimation { duration: Theme.durationNormal } }
            Behavior on y { NumberAnimation { duration: Theme.durationSlow; easing.type: Easing.OutCubic } }
        }
    }

    // ── 窗口状态持久化 ──────────────────────────────────
    closeListener: function (event) {
        if (root.visibility === Window.Windowed || root.visibility === Window.Maximized) {
            if (root.visibility === Window.Windowed)
                app.saveWindowSize(root.width, root.height)
            app.saveMaximized(root.visibility === Window.Maximized)
        }
        app.flush()
        root.destoryOnClose()
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
            if (app.expanded)
                app.setExpanded(false)
            else if (discover.detailId !== "")
                discover.closePlaylist()
        }
    }

    SettingsWindow {
        id: settingsWindow
    }

    LoginWindow {
        id: loginWindow
    }
}
