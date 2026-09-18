import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    设置窗口（标题栏齿轮按钮打开）。
*/
FluWindow {
    id: window

    width: 860
    height: 640
    minimumWidth: 760
    minimumHeight: 540
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

                    SectionHeader { Layout.fillWidth: true; title: "界面" }
                    SettingSwitch {
                        label: "启用动画"
                        description: "关闭后界面切换与悬停过渡会立即完成"
                        checked: settings.animations
                        onToggled: settings.setBool("appearance.animations", value)
                    }
                    SettingSwitch {
                        label: "展开左侧导航"
                        description: "关闭后导航栏折叠为图标模式"
                        checked: settings.navExpanded
                        onToggled: settings.setBool("appearance.nav_expanded", value)
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
                        onToggled: settings.setBool("sources.fallback", value)
                    }
                    SettingSwitch {
                        label: "优先原唱"
                        description: "在搜索结果中标记并置顶原唱版本（含百度百科兜底查询）"
                        checked: settings.preferOriginal
                        onToggled: settings.setBool("sources.prefer_original", value)
                    }
                    FluText {
                        Layout.fillWidth: true
                        text: "当前播放音量：" + player.volume + "%    ·    播放模式：" + player.modeLabel
                        font.pixelSize: 11
                        color: Theme.textTertiary
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
                                        ? account.vipLabel + " · UID " + account.userId
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
                        onToggled: settings.setBool("account.auto_login", value)
                    }
                    SettingSwitch {
                        label: "保存登录凭据"
                        description: "关闭后退出程序即需要重新登录"
                        checked: settings.saveCredentials
                        onToggled: settings.setBool("account.save_credentials", value)
                    }

                    SectionHeader { Layout.fillWidth: true; title: "凭据存储" }
                    SettingRow {
                        label: "凭据文件"
                        value: account.credentialPath
                        copyable: true
                    }
                    SettingRow {
                        label: "加密方式"
                        value: "AES-256-GCM · 密钥来源：" + account.keySource
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
                        onToggled: settings.setBool("lyrics.show_translation", value)
                    }
                    SettingSwitch {
                        label: "显示罗马音"
                        description: "日文歌曲的音译歌词"
                        checked: settings.showRomaji
                        onToggled: settings.setBool("lyrics.show_romaji", value)
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
                        onToggled: settings.setBool("local.scan_on_start", value)
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
                        onToggled: settings.setBool("storage.cache_media", value)
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

                    RowLayout {
                        spacing: 10
                        FluButton {
                            text: "恢复默认设置"
                            onClicked: resetDialog.open()
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
