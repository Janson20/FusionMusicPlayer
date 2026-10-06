import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    设置窗口（标题栏齿轮按钮打开）。
*/
FluWindow {
    id: window

    // 尺寸同样要过一遍屏幕：低分辨率下 860×640 的窗口会比桌面还高，
    // 底部的按钮就点不到了（见 bridges/app.py 的 fit_window）。
    readonly property var fitted: app.fitWindow(860, 640, 760, 540)

    width: fitted.width
    height: fitted.height
    minimumWidth: Math.min(760, fitted.width)
    minimumHeight: Math.min(540, fitted.height)
    title: "设置"
    visible: false
    // 关闭时只隐藏、不销毁：FluWindow 默认 closeDestory=true 会 deleteLater()，
    // 之后 QML 里的 id 就成了已释放对象，再调 showWindow() 会报
    // "Cannot call method 'showWindow' of null"。
    closeDestory: false
    fixSize: false
    showStayTop: false
    showDark: false
    showMaximize: true

    // 背景与主窗口一致（自定义背景图也在这里生效 —— 拖滑块就能当场看到效果）
    background: Component {
        AppBackground { }
    }

    // FluWindow 的基类 Component.onCompleted 会无条件 show()，
    // 不收回的话设置窗口会跟着主窗口一起弹出来。
    // 基类 onCompleted 先于派生组件执行，所以这里 hide() 是可靠的。
    Component.onCompleted: hide()

    property int section: 0

    readonly property var sections: [
        { name: "外观",    icon: FluentIcons.Color },
        { name: "播放",    icon: FluentIcons.Play },
        { name: "音源",    icon: FluentIcons.Globe },
        { name: "账号",    icon: FluentIcons.Accounts },
        { name: "歌词",    icon: FluentIcons.MusicInfo },
        { name: "本地音乐", icon: FluentIcons.Folder },
        { name: "存储",    icon: FluentIcons.Save },
        { name: "关于",    icon: FluentIcons.Info }
    ]

    function showWindow() {
        window.visible = true
        window.requestActivate()
        settings.refreshCache()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        // ── 左侧分区 ────────────────────────────────────────
        Rectangle {
            Layout.preferredWidth: 172
            Layout.fillHeight: true
            color: Theme.navBg

            Column {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 2

                Repeater {
                    model: window.sections
                    delegate: Rectangle {
                        required property var modelData
                        required property int index
                        width: parent.width
                        height: 40
                        radius: Theme.radiusSmall
                        color: window.section === index
                            ? Theme.accentSoft
                            : (secMouse.containsMouse ? FluTheme.itemHoverColor : "transparent")

                        Row {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.left: parent.left
                            anchors.leftMargin: 12
                            spacing: 10
                            FluIcon {
                                iconSource: modelData.icon
                                iconSize: 14
                                iconColor: window.section === index ? Theme.accent : Theme.textSecondary
                            }
                            FluText {
                                text: modelData.name
                                font.pixelSize: 12
                                font.weight: window.section === index ? Font.DemiBold : Font.Normal
                                color: window.section === index ? Theme.accent : Theme.textPrimary
                            }
                        }

                        MouseArea {
                            id: secMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: window.section = index
                        }
                    }
                }
            }
        }

        // ── 右侧内容 ────────────────────────────────────────
        Flickable {
            id: flick
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: width
            contentHeight: content.height + 44
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            ScrollBar.vertical: FluScrollBar { }

            ColumnLayout {
                id: content
                x: 26
                y: 22
                width: flick.width - 52
                spacing: 18

                // ═══ 外观 ═══════════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 0

                    SectionHeader { Layout.fillWidth: true; title: "主题模式" }
                    RowLayout {
                        spacing: 10
                        Repeater {
                            model: settings.themeOptions
                            delegate: Rectangle {
                                required property var modelData
                                width: 112
                                height: 62
                                radius: Theme.radius
                                color: settings.theme === modelData.id ? Theme.accentSoft : Theme.cardBg
                                border.width: settings.theme === modelData.id ? 2 : 1
                                border.color: settings.theme === modelData.id ? Theme.accent : Theme.border

                                ColumnLayout {
                                    anchors.centerIn: parent
                                    spacing: 6
                                    Rectangle {
                                        Layout.alignment: Qt.AlignHCenter
                                        width: 30
                                        height: 18
                                        radius: 4
                                        color: modelData.id === "dark" ? "#1E1D27"
                                             : (modelData.id === "light" ? "#FFFFFF" : "#8C8C99")
                                        border.width: 1
                                        border.color: Theme.border
                                    }
                                    FluText {
                                        Layout.alignment: Qt.AlignHCenter
                                        text: modelData.name
                                        font.pixelSize: 11
                                        color: settings.theme === modelData.id ? Theme.accent : Theme.textSecondary
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: settings.set("appearance.theme", modelData.id)
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    SectionHeader { Layout.fillWidth: true; title: "主色" }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 12
                        Repeater {
                            model: settings.accentPresets
                            delegate: ColumnLayout {
                                required property var modelData
                                spacing: 6
                                Rectangle {
                                    Layout.alignment: Qt.AlignHCenter
                                    width: 40
                                    height: 40
                                    radius: 20
                                    color: modelData.id
                                    border.width: settings.accent.toLowerCase() === modelData.id.toLowerCase() ? 3 : 0
                                    border.color: Theme.textPrimary
                                    FluIcon {
                                        anchors.centerIn: parent
                                        visible: settings.accent.toLowerCase() === modelData.id.toLowerCase()
                                        iconSource: FluentIcons.CheckMark
                                        iconSize: 15
                                        iconColor: "#FFFFFF"
                                    }
                                    MouseArea {
                                        anchors.fill: parent
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: settings.set("appearance.accent", modelData.id)
                                    }
                                }
                                FluText {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: modelData.name
                                    font.pixelSize: 10
                                    color: Theme.textTertiary
                                }
                            }
                        }
                    }

                    SectionHeader {
                        Layout.fillWidth: true
                        title: "背景图"
                        subtitle: settings.backgroundActive
                            ? "各区域按下面的「分区不透明度」压层，背景图从底下透出来"
                            : "选一张图当窗口背景；会复制进 data/backgrounds，原图挪走或删掉都不影响"
                    }
                    RowLayout {
                        spacing: 10
                        FluButton {
                            objectName: "backgroundPickButton"
                            text: settings.backgroundActive ? "更换图片…" : "选择图片…"
                            onClicked: backgroundDialog.open()
                        }
                        FluButton {
                            objectName: "backgroundClearButton"
                            text: "恢复纯色背景"
                            disabled: !settings.backgroundActive
                            onClicked: settings.clearBackgroundImage()
                        }
                        Item { Layout.fillWidth: true }
                    }
                    FluText {
                        Layout.fillWidth: true
                        visible: settings.backgroundImageInfo !== ""
                        text: settings.backgroundImageInfo
                        font.pixelSize: 11
                        color: settings.backgroundActive ? Theme.textTertiary : Theme.warning
                        wrapMode: Text.Wrap
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 3
                        columnSpacing: 12
                        rowSpacing: 8
                        // 没图时这几个旋钮没有可见效果，先灰掉，免得以为是坏的
                        enabled: settings.backgroundActive
                        opacity: settings.backgroundActive ? 1.0 : 0.5

                        FluText {
                            text: "透明度"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                        FluSlider {
                            objectName: "backgroundOpacitySlider"
                            Layout.preferredWidth: 240
                            from: 0
                            to: 100
                            stepSize: 1
                            value: settings.backgroundOpacity
                            tooltipEnabled: true
                            text: Math.round(value) + "%"
                            onMoved: settings.setInt("appearance.background_opacity", Math.round(value))
                        }
                        FluText {
                            Layout.preferredWidth: 42
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.backgroundOpacity + "%"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }

                        FluText {
                            text: "质感（磨砂）"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                        FluSlider {
                            objectName: "backgroundBlurSlider"
                            Layout.preferredWidth: 240
                            from: 0
                            to: 100
                            stepSize: 1
                            value: settings.backgroundBlur
                            tooltipEnabled: true
                            text: Math.round(value) + "%"
                            onMoved: settings.setInt("appearance.background_blur", Math.round(value))
                        }
                        FluText {
                            Layout.preferredWidth: 42
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.backgroundBlur + "%"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }

                        FluText {
                            text: "蒙版"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                        FluSlider {
                            objectName: "backgroundScrimSlider"
                            Layout.preferredWidth: 240
                            from: 0
                            to: 100
                            stepSize: 1
                            value: settings.backgroundScrim
                            tooltipEnabled: true
                            text: Math.round(value) + "%"
                            onMoved: settings.setInt("appearance.background_scrim", Math.round(value))
                        }
                        FluText {
                            Layout.preferredWidth: 42
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.backgroundScrim + "%"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }
                    }

                    SectionHeader {
                        Layout.fillWidth: true
                        title: "分区不透明度"
                        subtitle: "数字越小越透；内容区（主体）不铺面板色，所以图在主体上最清"
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 3
                        columnSpacing: 12
                        rowSpacing: 8
                        enabled: settings.backgroundActive
                        opacity: settings.backgroundActive ? 1.0 : 0.5

                        FluText {
                            text: "侧边栏"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                        FluSlider {
                            objectName: "surfaceSidebarSlider"
                            Layout.preferredWidth: 240
                            from: 0
                            to: 100
                            stepSize: 1
                            value: settings.surfaceSidebar
                            tooltipEnabled: true
                            text: Math.round(value) + "%"
                            onMoved: settings.setInt("appearance.surface_sidebar", Math.round(value))
                        }
                        FluText {
                            Layout.preferredWidth: 42
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.surfaceSidebar + "%"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }

                        FluText {
                            text: "底部播放栏"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                        FluSlider {
                            objectName: "surfaceBottomSlider"
                            Layout.preferredWidth: 240
                            from: 0
                            to: 100
                            stepSize: 1
                            value: settings.surfaceBottom
                            tooltipEnabled: true
                            text: Math.round(value) + "%"
                            onMoved: settings.setInt("appearance.surface_bottom", Math.round(value))
                        }
                        FluText {
                            Layout.preferredWidth: 42
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.surfaceBottom + "%"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }

                        FluText {
                            text: "歌词页 / 详情页"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                        FluSlider {
                            objectName: "surfaceOverlaySlider"
                            Layout.preferredWidth: 240
                            from: 0
                            to: 100
                            stepSize: 1
                            value: settings.surfaceOverlay
                            tooltipEnabled: true
                            text: Math.round(value) + "%"
                            onMoved: settings.setInt("appearance.surface_overlay", Math.round(value))
                        }
                        FluText {
                            Layout.preferredWidth: 42
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.surfaceOverlay + "%"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }

                        FluText {
                            text: "卡片 / 列表"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                            Layout.alignment: Qt.AlignVCenter
                        }
                        FluSlider {
                            objectName: "surfaceCardSlider"
                            Layout.preferredWidth: 240
                            from: 0
                            to: 100
                            stepSize: 1
                            value: settings.surfaceCard
                            tooltipEnabled: true
                            text: Math.round(value) + "%"
                            onMoved: settings.setInt("appearance.surface_card", Math.round(value))
                        }
                        FluText {
                            Layout.preferredWidth: 42
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.surfaceCard + "%"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "蒙版按主题取色（深色压黑、浅色提白）保证文字读得清；"
                            + "歌词页、歌单 / 专辑 / 歌手详情走同一个「覆盖层」参数，"
                            + "它们铺满内容区，底不透明就完全看不到图。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        wrapMode: Text.Wrap
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "磨砂（质感）是整窗一次模糊：分区只影响各自压的那层颜色深浅。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        wrapMode: Text.Wrap
                    }

                    SectionHeader { Layout.fillWidth: true; title: "界面" }
                    SettingSwitch {
                        label: "启用动画"
                        description: "关闭后界面切换与悬停过渡会立即完成"
                        checked: settings.animations
                        onToggled: function (value) { settings.setBool("appearance.animations", value) }
                    }
                    SettingSwitch {
                        label: "展开左侧导航"
                        description: "关闭后导航栏折叠为图标模式"
                        checked: settings.navExpanded
                        onToggled: function (value) { settings.setBool("appearance.nav_expanded", value) }
                    }

                    SectionHeader { Layout.fillWidth: true; title: "窗口" }
                    SettingSwitch {
                        objectName: "trayIconSwitch"
                        label: "显示托盘图标"
                        description: app.trayAvailable
                            ? "在系统托盘常驻：点图标回到主窗口，右键菜单能直接播放 / 暂停与切歌"
                            : "当前系统没有可用的通知区域（托盘），这个开关不起作用"
                        checked: app.trayEnabled
                        enabledControl: app.trayAvailable
                        onToggled: function (value) { app.setTrayEnabled(value) }
                    }
                    SectionHeader {
                        Layout.fillWidth: true
                        title: "关闭主窗口时"
                        subtitle: app.trayUsable
                            ? "选「每次询问」时，询问框里勾上「记住我的选择」就等于在这里改"
                            : "托盘用不了（系统不支持，或上面那个开关关着），关闭窗口就是退出程序"
                    }
                    FluComboBox {
                        objectName: "closeActionBox"
                        Layout.preferredWidth: 300
                        model: {
                            var names = []
                            var opts = app.closeActionOptions
                            for (var i = 0; i < opts.length; i++)
                                names.push(opts[i].name)
                            return names
                        }
                        currentIndex: {
                            var opts = app.closeActionOptions
                            for (var i = 0; i < opts.length; i++)
                                if (opts[i].id === app.closeAction) return i
                            return 0
                        }
                        onActivated: function (index) {
                            app.setCloseAction(app.closeActionOptions[index].id)
                        }
                    }
                }

                // ═══ 播放 ═══════════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 1

                    SectionHeader { Layout.fillWidth: true; title: "音质" }
                    FluComboBox {
                        Layout.preferredWidth: 300
                        model: {
                            var names = []
                            var opts = settings.qualityOptions
                            for (var i = 0; i < opts.length; i++)
                                names.push(opts[i].name)
                            return names
                        }
                        currentIndex: {
                            var opts = settings.qualityOptions
                            for (var i = 0; i < opts.length; i++)
                                if (opts[i].id === settings.quality) return i
                            return 0
                        }
                        onActivated: function (index) {
                            settings.set("playback.quality", settings.qualityOptions[index].id)
                        }
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "音质上限取决于账号权限：未登录最高 128K，音乐包 320K，黑胶 VIP 无损，SVIP 母带。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        wrapMode: Text.WordWrap
                    }

                    SectionHeader { Layout.fillWidth: true; title: "播放行为" }
                    SettingSwitch {
                        label: "跨音源自动兜底"
                        description: "当前音源无版权时，自动在其它平台搜索同款歌曲继续播放"
                        checked: settings.fallback
                        onToggled: function (value) { settings.setBool("sources.fallback", value) }
                    }
                    SettingSwitch {
                        label: "优先原唱"
                        description: "在搜索结果中标记并置顶原唱版本（含百度百科兜底查询）"
                        checked: settings.preferOriginal
                        onToggled: function (value) { settings.setBool("sources.prefer_original", value) }
                    }
                    SettingSwitch {
                        label: "启动时恢复上次播放"
                        description: "重新打开程序时把上次的播放队列与在播曲目摆回来，并从上次的进度接着放（不自动出声，按播放键才开始）"
                        checked: settings.restoreSession
                        onToggled: function (value) { settings.setBool("playback.restore_session", value) }
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "当前播放音量：" + player.volume + "%    ·    播放模式：" + player.modeLabel
                        font.pixelSize: 11
                        color: Theme.textTertiary
                    }

                    SectionHeader {
                        Layout.fillWidth: true
                        title: "音量均衡"
                        subtitle: "按 EBU R128 实测每首曲目的响度，自动把音量拉齐"
                    }
                    SettingSwitch {
                        objectName: "equalizeSwitch"
                        label: "启用音量均衡"
                        description: "后台分析曲目响度（约几秒一首，结果会缓存），播放时按增益调整；"
                                     + "只做整曲响度对齐，不做动态压缩"
                        checked: settings.equalize
                        onToggled: function (value) { settings.setBool("audio.equalize", value) }
                    }
                    RowLayout {
                        spacing: 12
                        FluText {
                            text: "目标响度"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                        }
                        FluComboBox {
                            objectName: "targetLufsBox"
                            Layout.preferredWidth: 260
                            enabled: settings.equalize
                            model: {
                                var names = []
                                var opts = settings.targetLufsOptions
                                for (var i = 0; i < opts.length; i++)
                                    names.push(opts[i].name)
                                return names
                            }
                            currentIndex: {
                                var opts = settings.targetLufsOptions
                                for (var i = 0; i < opts.length; i++)
                                    if (opts[i].id === settings.targetLufs) return i
                                return 2
                            }
                            onActivated: function (index) {
                                settings.set("audio.target_lufs",
                                             settings.targetLufsOptions[index].id)
                            }
                        }
                    }
                    SettingSwitch {
                        label: "允许抬高偏轻的曲目"
                        description: "关闭后只压低偏响的曲目、绝不抬升；开启时会按峰值留出余量防削波"
                        checked: settings.allowBoost
                        onToggled: function (value) { settings.setBool("audio.allow_boost", value) }
                    }
                    SettingSwitch {
                        label: "预取下一首"
                        description: "提前分析队列里的下一首，切歌时增益已经就绪（会多一次解析请求）"
                        checked: settings.prefetchLoudness
                        onToggled: function (value) { settings.setBool("audio.prefetch_next", value) }
                    }
                    SettingRow {
                        label: "已分析曲目"
                        value: settings.loudnessStats.measured + " 首"
                               + (settings.loudnessStats.pending > 0
                                  ? "（队列中 " + settings.loudnessStats.pending + " 首）" : "")
                    }
                    SettingRow {
                        label: "平均响度"
                        value: settings.loudnessStats.avgLoudness || "暂无数据"
                    }
                    SettingRow {
                        label: "分析数据占用"
                        value: settings.loudnessStats.size
                    }
                    RowLayout {
                        spacing: 10
                        FluText {
                            Layout.fillWidth: true
                            text: player.gainLabel ? ("当前曲目：" + player.gainLabel)
                                                   : "当前曲目尚未分析，或音量均衡未开启"
                            font.pixelSize: 11
                            color: Theme.textTertiary
                            wrapMode: Text.WordWrap
                        }
                        FluButton {
                            text: "清除分析数据"
                            onClicked: settings.clearLoudness()
                        }
                    }
                }

                // ═══ 音源 ═══════════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 2

                    SectionHeader {
                        Layout.fillWidth: true
                        title: "启用的音源"
                        subtitle: "搜索会并发请求已启用的音源"
                    }
                    Repeater {
                        model: settings.enabledSources
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 52
                            radius: Theme.radius
                            color: Theme.cardBg
                            border.width: 1
                            border.color: Theme.border

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 12
                                spacing: 12

                                FluText {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    text: modelData.name
                                    font.pixelSize: 13
                                    color: Theme.textPrimary
                                }
                                FluToggleSwitch {
                                    Layout.alignment: Qt.AlignVCenter
                                    checked: modelData.enabled
                                    text: ""
                                    clickListener: function () {
                                        settings.setSourceEnabled(modelData.id, !modelData.enabled)
                                    }
                                }
                            }
                        }
                    }
                }

                // ═══ 账号 ═══════════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 3

                    SectionHeader { Layout.fillWidth: true; title: "网易云音乐" }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 96
                        radius: Theme.radius
                        color: Theme.cardBg
                        border.width: 1
                        border.color: Theme.border

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 16

                            Rectangle {
                                Layout.preferredWidth: 56
                                Layout.preferredHeight: 56
                                Layout.alignment: Qt.AlignVCenter
                                radius: 28
                                color: Theme.accentSoft
                                clip: true

                                Image {
                                    anchors.fill: parent
                                    source: account.loggedIn ? account.avatar : ""
                                    visible: account.loggedIn && account.avatar !== ""
                                    fillMode: Image.PreserveAspectCrop
                                    sourceSize.width: 128
                                    sourceSize.height: 128
                                }
                                FluIcon {
                                    anchors.centerIn: parent
                                    visible: !account.loggedIn || account.avatar === ""
                                    iconSource: FluentIcons.Accounts
                                    iconSize: 24
                                    iconColor: Theme.accent
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                Layout.alignment: Qt.AlignVCenter
                                spacing: 4
                                FluText {
                                    text: account.loggedIn ? (account.nickname || "已登录") : "未登录"
                                    font.pixelSize: 15
                                    font.weight: Font.DemiBold
                                    color: Theme.textPrimary
                                }
                                FluText {
                                    text: account.loggedIn
                                        ? account.vipDetail
                                        : "登录后可播放 VIP 歌曲、同步歌单、获取翻译歌词"
                                    font.pixelSize: 11
                                    color: Theme.textTertiary
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                }
                                FluText {
                                    text: account.status
                                    font.pixelSize: 11
                                    color: Theme.accent
                                }
                            }

                            FluFilledButton {
                                Layout.alignment: Qt.AlignVCenter
                                text: account.loggedIn ? "退出登录" : "登录"
                                onClicked: {
                                    if (account.loggedIn)
                                        logoutDialog.open()
                                    else
                                        window.showLogin()
                                }
                            }
                        }
                    }

                    SettingSwitch {
                        label: "启动时自动恢复登录"
                        description: "使用程序目录下加密保存的凭据自动登录"
                        checked: settings.autoLogin
                        onToggled: function (value) { settings.setBool("account.auto_login", value) }
                    }
                    SettingSwitch {
                        label: "保存登录凭据"
                        description: "关闭后退出程序即需要重新登录"
                        checked: settings.saveCredentials
                        onToggled: function (value) { settings.setBool("account.save_credentials", value) }
                    }
                    SettingSwitch {
                        label: "自动续期登录凭据"
                        description: "凭据快到期时（默认 7 天内）自动向网易换一张新的，长期不用重新登录"
                        checked: settings.cookieRefreshDays > 0
                        onToggled: function (value) {
                            settings.setInt("account.cookie_refresh_days", value ? 7 : 0)
                        }
                    }

                    SectionHeader { Layout.fillWidth: true; title: "凭据存储" }

                    // 密钥解不开：数据目录大概是从别的电脑拷过来的。这里给一条出路。
                    Rectangle {
                        objectName: "keyProblemCard"
                        Layout.fillWidth: true
                        Layout.preferredHeight: keyProblem.implicitHeight + 24
                        visible: !account.keyUsable
                        radius: Theme.radius
                        color: Theme.dark
                            ? Qt.rgba(0.97, 0.44, 0.44, 0.12)
                            : Qt.rgba(0.86, 0.15, 0.15, 0.06)
                        border.width: 1
                        border.color: Theme.danger

                        ColumnLayout {
                            id: keyProblem
                            anchors {
                                left: parent.left
                                right: parent.right
                                top: parent.top
                                margins: 12
                            }
                            spacing: 8

                            FluText {
                                Layout.fillWidth: true
                                text: "凭据密钥在本机解不开"
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                                color: Theme.danger
                            }
                            FluText {
                                Layout.fillWidth: true
                                text: "主密钥由另一台电脑（或另一个 Windows 用户）的 DPAPI 保护，本机解不开，"
                                      + "已保存的登录状态没法恢复。开启下面的「便携模式」再重新登录一次，"
                                      + "以后把整个程序目录拷到哪台电脑都能保持登录。"
                                font.pixelSize: 11
                                color: Theme.textSecondary
                                wrapMode: Text.WordWrap
                            }
                            FluButton {
                                objectName: "rebuildKeyButton"
                                text: "重建密钥并重新登录"
                                onClicked: account.rebuildKey()
                            }
                        }
                    }

                    SettingSwitch {
                        objectName: "portableModeSwitch"
                        label: "便携模式（换台电脑也保持登录）"
                        description: "主密钥不再由本机 DPAPI 绑定：整个程序目录拷到别的电脑或别的 Windows 用户下，账号照样是登录状态。关掉后主密钥只在本机解得开 —— 更安全，但换电脑要重新登录。"
                        checked: account.portableMode
                        enabledControl: account.keyUsable
                        onToggled: function (value) { account.setPortableMode(value) }
                    }
                    FluText {
                        Layout.fillWidth: true
                        Layout.leftMargin: 2
                        text: account.portableHint
                        font.pixelSize: 11
                        color: account.keyUsable ? Theme.textTertiary : Theme.danger
                        wrapMode: Text.WordWrap
                    }

                    SettingRow {
                        label: "凭据文件"
                        value: account.credentialPath
                        copyable: true
                    }
                    SettingRow {
                        label: "加密方式"
                        value: "AES-256-GCM · 密钥来源：" + account.keySource
                    }
                    SettingRow {
                        objectName: "credentialExpiryRow"
                        label: "有效期"
                        value: account.credentialExpiry
                    }
                    FluText {
                        Layout.fillWidth: true
                        visible: account.credentialExpiring
                        text: "已进入自动续期窗口：下次启动会自动换发一张新凭据。"
                        font.pixelSize: 11
                        color: Theme.accent
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 10

                        FluButton {
                            objectName: "renewCredentialButton"
                            text: "立即续期"
                            enabled: account.loggedIn && !account.busy
                            onClicked: account.renewCredentials()
                        }
                        FluText {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            visible: !account.loggedIn
                            text: "登录后可续期"
                            font.pixelSize: 11
                            color: Theme.textTertiary
                        }
                        FluText {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            visible: account.loggedIn
                            text: "续期会向网易换发一张新的 MUSIC_U（有效期重新计时，旧的立刻失效与否由服务端决定）"
                            font.pixelSize: 11
                            color: Theme.textTertiary
                            wrapMode: Text.WordWrap
                        }
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "凭据以认证加密方式写入程序目录，密钥由 Windows DPAPI（当前用户）保护；"
                              + "设置环境变量 FUSION_MUSIC_MASTER_PASSWORD 可改用主密码派生密钥。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        wrapMode: Text.WordWrap
                    }
                }

                // ═══ 歌词 ═══════════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 4

                    SectionHeader { Layout.fillWidth: true; title: "歌词显示" }
                    SettingSwitch {
                        label: "显示翻译歌词"
                        description: "网易云部分歌曲提供官方翻译"
                        checked: settings.showTranslation
                        onToggled: function (value) { settings.setBool("lyrics.show_translation", value) }
                    }
                    SettingSwitch {
                        label: "显示罗马音"
                        description: "日文歌曲的音译歌词"
                        checked: settings.showRomaji
                        onToggled: function (value) { settings.setBool("lyrics.show_romaji", value) }
                    }
                    SettingSwitch {
                        objectName: "lyricDynamicSwitch"
                        label: "逐字（动态）歌词"
                        description: "唱到哪个字就点亮哪个字；网易云没有提供逐字歌词的"
                                     + "歌曲按行时间推算（效果略逊，但不再是整行突然亮起）"
                        checked: settings.lyricDynamic
                        onToggled: function (value) { settings.setBool("lyrics.dynamic", value) }
                    }

                    SectionHeader { Layout.fillWidth: true; title: "对齐方式" }
                    RowLayout {
                        spacing: 10
                        Repeater {
                            model: settings.lyricAlignOptions
                            delegate: Rectangle {
                                required property var modelData
                                Layout.preferredWidth: 92
                                Layout.preferredHeight: 34
                                radius: Theme.radiusSmall
                                color: settings.lyricAlignment === modelData.id
                                    ? Theme.accentSoft
                                    : Theme.cardBg
                                border.width: settings.lyricAlignment === modelData.id ? 2 : 1
                                border.color: settings.lyricAlignment === modelData.id
                                    ? Theme.accent
                                    : Theme.border

                                FluText {
                                    anchors.centerIn: parent
                                    text: modelData.name
                                    font.pixelSize: 12
                                    color: settings.lyricAlignment === modelData.id
                                        ? Theme.accent
                                        : Theme.textSecondary
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: settings.set("lyrics.alignment", modelData.id)
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "展开播放页的歌词默认居中显示，这里可以改成靠左或靠右。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        wrapMode: Text.WordWrap
                    }

                    SectionHeader { Layout.fillWidth: true; title: "字号" }
                    RowLayout {
                        spacing: 12
                        FluSlider {
                            Layout.preferredWidth: 260
                            from: 12
                            to: 26
                            stepSize: 1
                            value: settings.lyricFontSize
                            tooltipEnabled: true
                            text: Math.round(value) + " px"
                            onMoved: settings.setInt("lyrics.font_size", Math.round(value))
                        }
                        FluText {
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.lyricFontSize + " px"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "本地歌曲会读取同目录下的同名 .lrc 字幕文件。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                    }
                }

                // ═══ 本地音乐 ═══════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 5

                    SectionHeader {
                        Layout.fillWidth: true
                        title: "本地曲库"
                        subtitle: library.localModel.count + " 首"
                    }
                    SettingSwitch {
                        label: "启动时自动扫描"
                        description: "程序启动后自动重新扫描已添加的文件夹"
                        checked: settings.scanOnStart
                        onToggled: function (value) { settings.setBool("local.scan_on_start", value) }
                    }

                    SettingSwitch {
                        label: "自动匹配封面与歌词"
                        description: "扫描时按「歌名 + 歌手」在线匹配并核对时长，只写进曲库索引，不改动音乐文件；曲库很大时首次扫描会慢一些，之后重扫沿用上次结果"
                        checked: settings.matchLocalOnline
                        onToggled: function (value) { settings.setBool("local.match_online", value) }
                    }

                    Repeater {
                        model: library.localFolders
                        delegate: Rectangle {
                            required property string modelData
                            Layout.fillWidth: true
                            Layout.preferredHeight: 46
                            radius: Theme.radius
                            color: Theme.cardBg
                            border.width: 1
                            border.color: Theme.border

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 14
                                anchors.rightMargin: 10
                                spacing: 10
                                FluIcon {
                                    Layout.alignment: Qt.AlignVCenter
                                    iconSource: FluentIcons.Folder
                                    iconSize: 14
                                    iconColor: Theme.textSecondary
                                }
                                FluText {
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    text: modelData
                                    font.pixelSize: 12
                                    color: Theme.textPrimary
                                    elide: Text.ElideMiddle
                                }
                                FluIconButton {
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28
                                    Layout.alignment: Qt.AlignVCenter
                                    iconSize: 13
                                    iconSource: FluentIcons.Delete
                                    iconColor: Theme.textSecondary
                                    text: "移除"
                                    onClicked: library.removeLocalFolder(modelData)
                                }
                            }
                        }
                    }

                    FluText {
                        Layout.fillWidth: true
                        visible: library.localFolders.length === 0
                        text: "尚未添加文件夹，可在「本地音乐」页面添加。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                    }
                }

                // ═══ 存储 ═══════════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 6

                    SectionHeader { Layout.fillWidth: true; title: "缓存" }
                    SettingRow { label: "封面缓存"; value: settings.cacheStats.cover }
                    SettingRow { label: "歌词缓存"; value: settings.cacheStats.lyric }
                    SettingRow { label: "音频缓存"; value: settings.cacheStats.media }
                    SettingRow { label: "合计"; value: settings.cacheStats.total }

                    RowLayout {
                        spacing: 10
                        FluButton {
                            text: "刷新统计"
                            onClicked: settings.refreshCache()
                        }
                        FluButton {
                            text: "清空全部缓存"
                            onClicked: settings.clearCache()
                        }
                    }

                    SectionHeader { Layout.fillWidth: true; title: "音频缓存" }
                    SettingSwitch {
                        label: "缓存音频文件"
                        description: "需要自定义请求头的音源（如 B 站）本来就会下载到本地缓存"
                        checked: settings.cacheMedia
                        onToggled: function (value) { settings.setBool("storage.cache_media", value) }
                    }
                    RowLayout {
                        spacing: 12
                        FluText {
                            Layout.alignment: Qt.AlignVCenter
                            text: "缓存上限"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                        }
                        FluSlider {
                            Layout.preferredWidth: 240
                            from: 256
                            to: 8192
                            stepSize: 256
                            value: settings.mediaCacheLimit
                            tooltipEnabled: true
                            text: Math.round(value) + " MB"
                            onMoved: settings.setInt("storage.media_cache_limit_mb", Math.round(value))
                        }
                        FluText {
                            Layout.alignment: Qt.AlignVCenter
                            text: settings.mediaCacheLimit + " MB"
                            font.pixelSize: 12
                            color: Theme.textTertiary
                        }
                        FluButton {
                            text: "立即清理"
                            onClicked: settings.trimCache()
                        }
                        FluButton {
                            objectName: "dedupeCacheButton"
                            text: "清理重复文件"
                            onClicked: settings.dedupeCache()
                        }
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "「缓存音频文件」开着时，同一首歌曾经会因为播放地址每次都变"
                              + "而重复存好几份（旧版本的问题，已修复）。这里用来清理"
                              + "已经堆在盘上的那些重复文件，只比对大小相同的，保留最近用过的一份。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        wrapMode: Text.WordWrap
                    }

                    SectionHeader { Layout.fillWidth: true; title: "目录" }
                    SettingRow { label: "程序目录"; value: settings.programDir; copyable: true }
                    SettingRow { label: "数据目录"; value: settings.dataDir; copyable: true }
                    SettingRow { label: "缓存目录"; value: settings.cacheDir; copyable: true }
                    SettingRow { label: "下载目录"; value: settings.downloadDir; copyable: true }

                    RowLayout {
                        spacing: 10
                        FluButton {
                            text: "打开数据目录"
                            onClicked: settings.openPath(settings.dataDir)
                        }
                        FluButton {
                            text: "打开缓存目录"
                            onClicked: settings.openPath(settings.cacheDir)
                        }
                    }
                }

                // ═══ 关于 ═══════════════════════════════════
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    visible: window.section === 7

                    RowLayout {
                        spacing: 16
                        Rectangle {
                            Layout.preferredWidth: 64
                            Layout.preferredHeight: 64
                            radius: 18
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Theme.accent }
                                GradientStop { position: 1.0; color: Theme.accentGradientEnd }
                            }
                            FluIcon {
                                anchors.centerIn: parent
                                iconSource: FluentIcons.MusicNote
                                iconSize: 30
                                iconColor: Theme.accentText
                            }
                        }
                        ColumnLayout {
                            spacing: 4
                            FluText {
                                text: "Fusion Music Player"
                                font.pixelSize: 20
                                font.weight: Font.Bold
                                color: Theme.textPrimary
                            }
                            FluText {
                                text: "版本 " + app.version + " · 基于 PySide6 + FluentUI QML"
                                font.pixelSize: 12
                                color: Theme.textTertiary
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }

                    FluText {
                        Layout.fillWidth: true
                        text: "音乐源、原生加密与跨源兜底算法来自 FMCL（GPL-3.0-only）的 ui/music_source 模块；"
                              + "界面、播放引擎、歌单与凭据存储已用 PySide6 + QML 重新实现。"
                        font.pixelSize: 12
                        color: Theme.textSecondary
                        wrapMode: Text.WordWrap
                    }

                    SettingRow { label: "音源数量"; value: app.sources.length + " 个" }
                    SettingRow { label: "本地歌单"; value: library.playlists.length + " 个" }
                    SettingRow { label: "我喜欢"; value: library.favoritesModel.count + " 首" }
                    SettingRow { label: "播放历史"; value: library.historyModel.count + " 条" }

                    SectionHeader {
                        Layout.fillWidth: true
                        title: "更新"
                        subtitle: "从 GitHub Releases 检查新版本"
                    }
                    SettingRow { label: "当前版本"; value: updater.currentVersion; copyable: true }
                    SettingRow {
                        label: "最新版本"
                        value: updater.latestVersion
                               ? (updater.latestVersion + (updater.publishedAt ? "（" + updater.publishedAt + "）" : ""))
                               : "尚未检查"
                    }
                    SettingRow {
                        label: "状态"
                        value: updater.statusText || "未检查"
                    }
                    FluText {
                        Layout.fillWidth: true
                        visible: updater.errorText !== ""
                        text: updater.errorText
                        font.pixelSize: 11
                        color: Theme.danger
                        wrapMode: Text.WordWrap
                    }
                    ProgressBar {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 6
                        visible: updater.state === "downloading" || updater.state === "installing"
                        from: 0
                        to: 1
                        value: updater.progress
                    }

                    RowLayout {
                        spacing: 10
                        FluButton {
                            objectName: "checkUpdateButton"
                            text: updater.state === "checking" ? "检查中…" : "检查更新"
                            enabled: !updater.busy
                            onClicked: updater.checkNow()
                        }
                        FluButton {
                            text: updater.state === "ready" ? "重新下载" : "下载更新"
                            visible: updater.updateAvailable && updater.state !== "ready"
                            enabled: !updater.busy && updater.canInstall
                            onClicked: updater.download()
                        }
                        FluButton {
                            text: "取消下载"
                            visible: updater.state === "downloading"
                            onClicked: updater.cancelDownload()
                        }
                        FluButton {
                            objectName: "installUpdateButton"
                            text: "立即安装并重启"
                            visible: updater.ready
                            enabled: updater.canInstall
                            onClicked: updater.installAndRestart()
                        }
                        FluButton {
                            text: "打开发布页"
                            onClicked: updater.openReleasePage()
                        }
                        Item { Layout.fillWidth: true }
                    }
                    FluText {
                        Layout.fillWidth: true
                        visible: updater.installHint !== ""
                        text: updater.installHint
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        wrapMode: Text.WordWrap
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        visible: updater.releaseNotes !== ""
                        spacing: 6
                        FluText {
                            text: "更新说明"
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                        }
                        Flickable {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 150
                            contentWidth: width
                            contentHeight: notesText.height + 8
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: FluScrollBar { }
                            FluText {
                                id: notesText
                                width: parent.width
                                text: updater.releaseNotes
                                font.pixelSize: 11
                                color: Theme.textSecondary
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    SettingSwitch {
                        objectName: "autoCheckUpdateSwitch"
                        label: "自动检查更新"
                        description: "启动后静默检查一次，并按下面的间隔定期检查；只提示，不会自动安装"
                        checked: updater.autoCheck
                        onToggled: function (value) { updater.setAutoCheck(value) }
                    }
                    RowLayout {
                        spacing: 12
                        FluText {
                            text: "检查间隔"
                            font.pixelSize: 12
                            color: Theme.textSecondary
                        }
                        FluComboBox {
                            Layout.preferredWidth: 180
                            enabled: updater.autoCheck
                            model: {
                                var names = []
                                var opts = updater.intervalOptions
                                for (var i = 0; i < opts.length; i++)
                                    names.push(opts[i].name)
                                return names
                            }
                            currentIndex: {
                                var opts = updater.intervalOptions
                                for (var i = 0; i < opts.length; i++)
                                    if (opts[i].id === updater.intervalHours) return i
                                return 1
                            }
                            onActivated: function (index) {
                                updater.setIntervalHours(updater.intervalOptions[index].id)
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    SettingSwitch {
                        label: "包含预发布版本"
                        description: "开启后连 beta / rc 一起提示（正式版优先）"
                        checked: updater.includePrerelease
                        onToggled: function (value) { updater.setIncludePrerelease(value) }
                    }

                    RowLayout {
                        spacing: 10
                        FluButton {
                            text: "恢复默认设置"
                            onClicked: resetDialog.open()
                        }
                        FluButton {
                            text: "打开更新日志"
                            visible: updater.lastLogTail !== ""
                            onClicked: updater.openUpdateLog()
                        }
                    }
                }

                Item { Layout.preferredHeight: 20 }
            }
        }
    }

    function showLogin() {
        window.visible = false
        app.openLogin()
    }

    // 选背景图。用 FileDialog（和本地音乐页选文件夹同一套做法）：让用户手打
    // 图片路径既容易打错也没法预览。入库、格式校验、旧图清理都在 Python 侧
    // （settings.applyBackgroundImage），失败会弹提示且不动原有背景。
    FileDialog {
        id: backgroundDialog
        objectName: "backgroundImageDialog"
        title: "选择背景图片"
        nameFilters: ["图片 (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.tif *.tiff *.svg)",
                      "所有文件 (*)"]
        onAccepted: settings.applyBackgroundImage(selectedFile.toString())
    }

    FluContentDialog {
        id: logoutDialog
        title: "退出登录"
        message: "将删除本地加密保存的网易云凭据，下次需要重新登录。"
        positiveText: "退出"
        negativeText: "取消"
        buttonFlags: FluContentDialogType.NegativeButton | FluContentDialogType.PositiveButton
        onPositiveClicked: {
            account.logout()
            close()
        }
    }

    FluContentDialog {
        id: resetDialog
        title: "恢复默认设置"
        message: "所有设置项将恢复默认值，歌单与登录状态不受影响。确定继续？"
        positiveText: "恢复"
        negativeText: "取消"
        buttonFlags: FluContentDialogType.NegativeButton | FluContentDialogType.PositiveButton
        onPositiveClicked: {
            settings.resetAll()
            close()
        }
    }
}
