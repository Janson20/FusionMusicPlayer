import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"
import "../ArtistNames.js" as ArtistNames

/*!
    展开播放页：大封面 + 滚动歌词 / 歌曲百科 + 完整控制。

    对应草图中底部播放栏右侧的 ^ 展开态。右侧是一块卡片，顶上两个标签页
    「歌词 / 百科」—— 与网易云客户端的歌曲详情页一致。
*/
Item {
    id: control
    objectName: "nowPlayingPanel"

    // 右侧卡片是否展开。收起时两侧的弹性空白把封面区推到水平正中。
    property bool showLyrics: true

    // 右侧卡片的标签页：0 = 歌词，1 = 百科
    property int tab: 0

    //: 标签页定义（``id`` 与上面的 tab 对应）
    readonly property var tabs: [
        { "id": 0, "name": "歌词" },
        { "id": 1, "name": "百科" }
    ]

    // 封面尺寸按可用高度推导（固定值，避免 ColumnLayout 内的循环依赖）
    readonly property int coverSize: Math.max(180, Math.min(320, control.height * 0.34))

    // 歌词文字对齐：默认居中，可在「设置 → 歌词 → 对齐方式」改为靠左 / 靠右
    readonly property int lyricAlign: {
        switch (settings.lyricAlignment) {
        case "left": return Text.AlignLeft
        case "right": return Text.AlignRight
        default: return Text.AlignHCenter
        }
    }

    // 百科只在「页面真的露出来 + 卡片展开 + 停在百科标签」时才去取数 ——
    // 否则每切一首歌都要白跑一次接口（还要顺带搜一次歌曲、一次专辑）
    readonly property bool wikiActive: control.visible && control.showLyrics && control.tab === 1
    onWikiActiveChanged: wiki.setActive(control.wikiActive)
    Component.onCompleted: wiki.setActive(control.wikiActive)

    signal collapseRequested

    // 点歌手名进歌手页。歌手页在主界面那一层，展开播放页盖在它上面，
    // 所以先收起来再打开，否则打开了个看不见的页面。
    function openArtist(name) {
        if (name === "")
            return
        if (app.expanded)
            app.setExpanded(false)
        artist.openByName(name)
    }

    // 点专辑名进专辑页，同上
    function openAlbum() {
        if (player.album === "")
            return
        if (app.expanded)
            app.setExpanded(false)
        album.openById(player.albumId, player.album)
    }

    // ── 事件遮罩 ────────────────────────────────────────
    // 面板根节点只是个普通 Item：空白处不处理鼠标事件，事件会继续往下找
    // 能接收的项，于是会穿透到底下的导航栏 / 页面 / 播放栏（展开态能点到
    // 导航项）。用它兜住空白区域的事件，并顺手吃掉滚轮，避免滚动穿透。
    // 必须声明在其它子项之前，可交互控件才仍然优先拿到事件。
    MouseArea {
        objectName: "nowPlayingBlocker"
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onWheel: function (wheel) { wheel.accepted = true }
    }

    // ── 背景：品牌色柔和渐变 ────────────────────────────
    Rectangle {
        anchors.fill: parent
        color: Theme.windowBg

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop {
                    position: 0.0
                    color: Theme.dark
                        ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.16)
                        : Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.08)
                }
                GradientStop { position: 0.55; color: "transparent" }
            }
        }
    }

    // ── 顶部工具条 ──────────────────────────────────────
    RowLayout {
        id: topBar
        anchors {
            top: parent.top
            left: parent.left
            right: parent.right
            margins: 20
        }
        spacing: 8

        FluText {
            Layout.fillWidth: true
            text: player.sourceLabel
            font.pixelSize: 11
            color: Theme.textTertiary
            elide: Text.ElideRight
            Layout.alignment: Qt.AlignVCenter
        }

        // 歌词 / 百科的切换挪进了右侧卡片顶部（与歌曲详情页一致），
        // 这里只留「收起」，卡片整体显示与否由底部控制条上的按钮管。
        FluIconButton {
            objectName: "nowPlayingCollapseButton"
            Layout.preferredWidth: 34
            Layout.preferredHeight: 34
            Layout.alignment: Qt.AlignVCenter
            iconSize: 17
            iconSource: FluentIcons.ChevronDown
            iconColor: Theme.textSecondary
            text: "收起"
            onClicked: control.collapseRequested()
        }
    }

    // ── 主体 ────────────────────────────────────────────
    RowLayout {
        anchors {
            top: topBar.bottom
            topMargin: 8
            left: parent.left
            right: parent.right
            bottom: controls.top
            bottomMargin: 8
            leftMargin: 40
            rightMargin: 40
        }
        spacing: 36

        // 歌词隐藏时用它两侧的弹性空白把封面区推到水平正中
        // （不可见的项不参与布局，所以歌词显示时这两个占位等于不存在）
        Item {
            Layout.fillWidth: true
            visible: !control.showLyrics
        }

        // 左：封面与信息
        ColumnLayout {
            id: leftColumn
            objectName: "nowPlayingCoverColumn"
            Layout.preferredWidth: control.coverSize
            Layout.minimumWidth: 180
            Layout.maximumWidth: 330
            Layout.fillWidth: false
            Layout.fillHeight: true
            spacing: 16

            Item { Layout.fillHeight: true }

            Item {
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: control.coverSize
                Layout.preferredHeight: control.coverSize

                CoverArt {
                    anchors.fill: parent
                    radiusSize: Theme.radiusLarge
                    source: player.coverUrl
                }

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusLarge
                    color: "transparent"
                    border.width: 1
                    border.color: Theme.dark ? "#33FFFFFF" : "#12000000"
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6

                FluText {
                    Layout.fillWidth: true
                    text: player.title !== "" ? player.title : "未在播放"
                    font.pixelSize: 22
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                    elide: Text.ElideRight
                    horizontalAlignment: Text.AlignHCenter
                }

                // 歌手名可点（进歌手页）
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 0
                    visible: player.artist !== ""

                    Repeater {
                        model: ArtistNames.split(player.artist)
                        delegate: FluText {
                            required property string modelData
                            required property int index

                            objectName: "nowPlayingArtistLink"
                            Layout.alignment: Qt.AlignVCenter
                            Layout.maximumWidth: 220
                            text: (index > 0 ? " / " : "") + modelData
                            font.pixelSize: 13
                            font.underline: npArtistMouse.containsMouse
                            color: npArtistMouse.containsMouse ? Theme.accent : Theme.textSecondary
                            elide: Text.ElideRight

                            MouseArea {
                                id: npArtistMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: control.openArtist(modelData)
                            }
                        }
                    }
                }

                // 专辑名可点（进专辑页）
                FluText {
                    objectName: "nowPlayingAlbumLink"
                    Layout.alignment: Qt.AlignHCenter
                    Layout.maximumWidth: 340
                    visible: player.album !== ""
                    text: player.album
                    font.pixelSize: 12
                    font.underline: npAlbumMouse.containsMouse
                    color: npAlbumMouse.containsMouse ? Theme.accent : Theme.textTertiary
                    elide: Text.ElideRight

                    MouseArea {
                        id: npAlbumMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: control.openAlbum()
                    }
                }

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 4
                    spacing: 8

                    Rectangle {
                        Layout.preferredWidth: qText2.implicitWidth + 16
                        Layout.preferredHeight: 20
                        radius: 10
                        color: Theme.accentSoft
                        FluText {
                            id: qText2
                            anchors.centerIn: parent
                            text: player.qualityLabel
                            font.pixelSize: 10
                            color: Theme.accent
                        }
                    }

                    FluIconButton {
                        Layout.preferredWidth: 30
                        Layout.preferredHeight: 30
                        iconSize: 15
                        iconSource: player.isFavorite ? FluentIcons.HeartFill : FluentIcons.Heart
                        iconColor: player.isFavorite ? Theme.accent : Theme.textSecondary
                        text: player.isFavorite ? "取消喜欢" : "我喜欢"
                        visible: player.title !== ""
                        onClicked: player.toggleFavorite()
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }

        Item {
            Layout.fillWidth: true
            visible: !control.showLyrics
        }

        // 右：歌词 / 百科（顶部两个标签页，与歌曲详情页一致）
        Rectangle {
            id: rightCard
            Layout.fillWidth: true
            Layout.minimumWidth: 260
            Layout.fillHeight: true
            visible: control.showLyrics
            radius: Theme.radiusLarge
            color: Theme.dark ? Qt.rgba(1, 1, 1, 0.03) : Qt.rgba(1, 1, 1, 0.55)
            border.width: 1
            border.color: Theme.border
            clip: true

            // ── 标签栏 ──────────────────────────────────────
            RowLayout {
                id: tabBar
                anchors {
                    top: parent.top
                    left: parent.left
                    right: parent.right
                    margins: 14
                }
                spacing: 8

                Repeater {
                    model: control.tabs
                    delegate: Rectangle {
                        objectName: "nowPlayingTab"
                        required property var modelData

                        implicitWidth: tabLabel.implicitWidth + 26
                        implicitHeight: 28
                        radius: 14
                        color: control.tab === modelData.id
                            ? Theme.accent
                            : (tabMouse.containsMouse ? Theme.accentSoft : (Theme.dark ? "#252431" : "#F0EFF7"))
                        Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                        FluText {
                            id: tabLabel
                            anchors.centerIn: parent
                            text: modelData.name
                            font.pixelSize: 12
                            font.weight: control.tab === modelData.id ? Font.DemiBold : Font.Normal
                            color: control.tab === modelData.id ? Theme.accentText : Theme.textSecondary
                        }

                        MouseArea {
                            id: tabMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: control.tab = modelData.id
                        }
                    }
                }

                Item { Layout.fillWidth: true }
            }

            // ── 歌词 ────────────────────────────────────────
            ListView {
                id: lyricView
                objectName: "lyricView"
                anchors.fill: parent
                anchors.topMargin: 62
                anchors.bottomMargin: 74
                // 左右留白取一样宽，居中排版才不会整体偏右
                anchors.leftMargin: 20
                anchors.rightMargin: 20
                visible: control.tab === 0
                clip: true
                spacing: 6
                model: player.lyricLines
                currentIndex: player.lyricIndex
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: FluScrollBar { }

                onCurrentIndexChanged: {
                    if (currentIndex >= 0 && count > 0)
                        positionViewAtIndex(currentIndex, ListView.Center)
                }

                Behavior on contentY {
                    NumberAnimation { duration: 320; easing.type: Easing.OutCubic }
                }

                delegate: Item {
                    id: lyricRow
                    required property var modelData
                    required property int index

                    width: lyricView.width
                    height: mainText.implicitHeight + (subText.visible ? subText.implicitHeight + 4 : 0) + 14

                    readonly property bool active: lyricRow.index === player.lyricIndex

                    FluText {
                        id: mainText
                        width: parent.width
                        text: lyricRow.modelData.text
                        font.pixelSize: lyricRow.active ? 19 : 15
                        font.weight: lyricRow.active ? Font.Bold : Font.Normal
                        color: lyricRow.active
                            ? Theme.accent
                            : (lyricRow.index < player.lyricIndex ? Theme.textTertiary : Theme.textSecondary)
                        horizontalAlignment: control.lyricAlign
                        wrapMode: Text.WordWrap
                        elide: Text.ElideRight
                        maximumLineCount: 2
                        opacity: lyricRow.active ? 1.0 : 0.62

                        Behavior on font.pixelSize {
                            NumberAnimation { duration: Theme.durationNormal }
                        }
                        Behavior on opacity { NumberAnimation { duration: Theme.durationNormal } }
                    }

                    FluText {
                        id: subText
                        width: parent.width
                        anchors.top: mainText.bottom
                        anchors.topMargin: 4
                        visible: lyricRow.modelData.sub !== ""
                        text: lyricRow.modelData.sub
                        font.pixelSize: 12
                        color: Theme.textTertiary
                        horizontalAlignment: control.lyricAlign
                        wrapMode: Text.WordWrap
                        elide: Text.ElideRight
                        maximumLineCount: 2
                        opacity: lyricRow.active ? 0.95 : 0.5
                    }
                }
            }

            // 无歌词占位
            ColumnLayout {
                anchors.centerIn: parent
                visible: control.tab === 0 && !player.hasLyrics
                spacing: 10

                FluIcon {
                    Layout.alignment: Qt.AlignHCenter
                    iconSource: FluentIcons.MusicInfo
                    iconSize: 40
                    iconColor: Theme.dark ? "#3A3846" : "#CFCCE0"
                }
                FluText {
                    Layout.alignment: Qt.AlignHCenter
                    text: player.loading ? "正在获取歌词…" : "暂无歌词"
                    font.pixelSize: 13
                    color: Theme.textTertiary
                }
            }

            // ── 歌曲百科 ────────────────────────────────────
            Flickable {
                id: wikiPane
                objectName: "songWikiPane"
                anchors.fill: parent
                anchors.topMargin: 58
                anchors.bottomMargin: 16
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                visible: control.tab === 1
                clip: true
                contentWidth: width
                contentHeight: wikiColumn.height + 8
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: FluScrollBar { }

                ColumnLayout {
                    id: wikiColumn
                    width: wikiPane.width
                    spacing: 2

                    FluText {
                        Layout.leftMargin: 10
                        Layout.topMargin: 4
                        Layout.bottomMargin: 8
                        text: "音乐百科"
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                    }

                    Repeater {
                        model: wiki.rows
                        delegate: RowLayout {
                            objectName: "songWikiRow"
                            required property var modelData

                            Layout.fillWidth: true
                            Layout.leftMargin: 10
                            Layout.rightMargin: 10
                            Layout.topMargin: 5
                            Layout.bottomMargin: 5
                            spacing: 14

                            FluText {
                                Layout.preferredWidth: 68
                                Layout.alignment: Qt.AlignTop
                                text: modelData.label
                                font.pixelSize: 13
                                color: Theme.textTertiary
                            }

                            FluText {
                                Layout.fillWidth: true
                                text: modelData.value
                                font.pixelSize: 13
                                color: Theme.textPrimary
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }

            // 无百科占位（可能是还没开始播放，也可能网易云没收录）
            ColumnLayout {
                anchors.centerIn: parent
                visible: control.tab === 1 && !wiki.hasRows
                spacing: 10

                FluIcon {
                    Layout.alignment: Qt.AlignHCenter
                    iconSource: FluentIcons.KnowledgeArticle
                    iconSize: 40
                    iconColor: Theme.dark ? "#3A3846" : "#CFCCE0"
                }
                FluText {
                    Layout.alignment: Qt.AlignHCenter
                    text: wiki.loading ? "正在获取百科…" : wiki.hint
                    font.pixelSize: 13
                    color: Theme.textTertiary
                }
            }
        }
    }

    // ── 底部控制（进度 + 传输）──────────────────────────
    ColumnLayout {
        id: controls
        anchors {
            left: parent.left
            right: parent.right
            bottom: parent.bottom
            bottomMargin: 30
        }
        spacing: 16

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Math.min(720, control.width - 88)
            spacing: 12

            FluText {
                text: player.positionText
                font.pixelSize: 11
                color: Theme.textTertiary
                Layout.preferredWidth: 44
                horizontalAlignment: Text.AlignRight
            }

            FluSlider {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                from: 0
                to: player.duration > 0 ? player.duration : 1
                value: player.duration > 0 ? player.position : 0
                enabled: player.duration > 0
                tooltipEnabled: false
                onMoved: {
                    if (player.duration > 0)
                        player.seek(Math.round(value))
                }
            }

            FluText {
                text: player.durationText
                font.pixelSize: 11
                color: Theme.textTertiary
                Layout.preferredWidth: 44
            }
        }

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 26

            FluIconButton {
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                iconSize: 16
                iconSource: {
                    switch (player.mode) {
                    case 0: return FluentIcons.RepeatOff
                    case 1: return FluentIcons.RepeatAll
                    case 2: return FluentIcons.RepeatOne
                    default: return FluentIcons.Shuffle
                    }
                }
                iconColor: player.mode === 0 ? Theme.textSecondary : Theme.accent
                text: player.modeLabel
                onClicked: player.cycleMode()
            }

            FluIconButton {
                Layout.preferredWidth: 46
                Layout.preferredHeight: 46
                iconSize: 22
                iconSource: FluentIcons.Previous
                text: "上一首"
                onClicked: player.previous()
            }

            Rectangle {
                Layout.preferredWidth: 58
                Layout.preferredHeight: 58
                radius: 29
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Theme.accent }
                    GradientStop { position: 1.0; color: Theme.accentGradientEnd }
                }
                scale: bigPlayMouse.pressed ? 0.94 : (bigPlayMouse.containsMouse ? 1.04 : 1.0)
                Behavior on scale { NumberAnimation { duration: Theme.durationFast } }

                FluProgressRing {
                    anchors.centerIn: parent
                    width: 28
                    height: 28
                    strokeWidth: 3
                    color: Theme.accentText
                    visible: player.loading
                }

                FluIcon {
                    anchors.centerIn: parent
                    visible: !player.loading
                    iconSource: player.playing ? FluentIcons.Pause : FluentIcons.PlaySolid
                    iconSize: 22
                    iconColor: Theme.accentText
                }

                MouseArea {
                    id: bigPlayMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: player.toggle()
                }
            }

            FluIconButton {
                Layout.preferredWidth: 46
                Layout.preferredHeight: 46
                iconSize: 22
                iconSource: FluentIcons.Next
                text: "下一首"
                onClicked: player.next()
            }

            // 收起 / 展开右侧卡片（歌词与百科在一起），收起后封面区水平居中
            FluIconButton {
                objectName: "nowPlayingPanelToggle"
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                iconSize: 16
                iconSource: FluentIcons.MusicInfo
                iconColor: control.showLyrics ? Theme.accent : Theme.textSecondary
                text: control.showLyrics ? "隐藏歌词与百科" : "显示歌词与百科"
                onClicked: control.showLyrics = !control.showLyrics
            }
        }
    }
}
