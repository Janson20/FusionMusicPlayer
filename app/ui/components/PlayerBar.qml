import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../ArtistNames.js" as ArtistNames

/*!
    底部播放栏（对应草图：左侧封面 / 中间播放控制 / 右侧展开箭头）。

    在草图结构上补齐了真实播放器必需的信息：歌曲标题、进度条、音量、
    播放模式与队列入口；整体高度 94px，视觉重心仍在中间的传输控件。
*/
Rectangle {
    id: control

    objectName: "playerBar"

    property bool expanded: false
    property bool canExpand: true

    signal expandToggled
    signal openNowPlaying

    // 点歌手名进歌手页。歌手行已按 ArtistNames 拆成单个名字（见下方 Repeater），
    // 这里再 first() 一次只是容错：万一传进来的是整串，也别拿整串去找歌手。
    function openArtist(name) {
        var single = ArtistNames.first(name)
        if (single !== "")
            artist.openByName(single)
    }

    color: Theme.barBg

    // 顶部分隔线
    Rectangle {
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: 1
        color: Theme.border
    }

    // ── 进度条（贴底细线，可拖动）────────────────────────
    Item {
        id: progressTrack
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: 3
        visible: !control.expanded

        Rectangle {
            anchors.fill: parent
            color: Theme.dark ? "#2A2833" : "#E8E7F1"
        }
        Rectangle {
            height: parent.height
            width: player.duration > 0
                ? parent.width * Math.min(1, player.position / player.duration)
                : 0
            color: Theme.accent
        }
        MouseArea {
            anchors.fill: parent
            anchors.topMargin: -6
            anchors.bottomMargin: -4
            cursorShape: Qt.PointingHandCursor
            onPositionChanged: function (mouse) {
                if (pressed && player.duration > 0)
                    player.seek(Math.round(mouse.x / width * player.duration))
            }
            onPressed: function (mouse) {
                if (player.duration > 0)
                    player.seek(Math.round(mouse.x / width * player.duration))
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.bottomMargin: 3
        spacing: 16

        // ══ 左：封面 + 曲目信息 ══════════════════════════
        RowLayout {
            Layout.preferredWidth: 300
            Layout.minimumWidth: 200
            Layout.fillHeight: true
            spacing: 12

            Item {
                Layout.preferredWidth: 58
                Layout.preferredHeight: 58
                Layout.alignment: Qt.AlignVCenter

                CoverArt {
                    anchors.fill: parent
                    radiusSize: Theme.radius
                    source: player.coverUrl
                }

                // 悬停时显示「展开」
                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radius
                    color: Qt.rgba(0, 0, 0, 0.45)
                    opacity: coverMouse.containsMouse && control.canExpand ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
                    FluIcon {
                        anchors.centerIn: parent
                        iconSource: FluentIcons.ChevronUp
                        iconSize: 18
                        iconColor: "#FFFFFF"
                    }
                }

                // 左键展开播放页，右键存封面
                MouseArea {
                    id: coverMouse
                    objectName: "playerBarCoverArea"
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: function (mouse) {
                        if (mouse.button === Qt.RightButton)
                            coverMenu.popup()
                        else if (control.canExpand)
                            control.openNowPlaying()
                    }
                }

                FluMenu {
                    id: coverMenu
                    objectName: "playerBarCoverMenu"
                    FluMenuItem {
                        objectName: "playerBarSaveCoverItem"
                        text: "保存封面…"
                        enabled: player.currentTrack !== null
                        onClicked: coverSaveDialog.openFor(player.currentTrack)
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 4

                FluText {
                    objectName: "playerBarTitle"
                    Layout.fillWidth: true
                    text: player.title !== "" ? player.title : "未在播放"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    color: player.title !== "" ? Theme.textPrimary : Theme.textTertiary
                    elide: Text.ElideRight
                }

                // 歌手行：与曲目行、展开播放页同一套渲染 —— 每位歌手单独可点、
                // 分隔符是独立项。以前这里把整串歌手名塞进一个 Text（"神田沙也加、
                // DECO*27" 看着像**一个**名字，点进去也只进第一位），与别处
                // " / " 分开的样子对不上。
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    visible: player.artist !== ""

                    Repeater {
                        // 播放栏窄（歌手区原本只给 200px），铺开 2 位，其余进「等 N 人」菜单
                        model: ArtistNames.linkParts(player.artist, 2)

                        delegate: FluText {
                            required property var modelData

                            objectName: modelData.more
                                ? "playerBarArtistMore"
                                : (modelData.separator ? "playerBarArtistSep"
                                                       : "playerBarArtistLink")
                            Layout.alignment: Qt.AlignVCenter
                            Layout.maximumWidth: modelData.separator ? Number.POSITIVE_INFINITY : 110
                            text: modelData.text
                            font.pixelSize: 11
                            font.underline: barArtistMouse.containsMouse && !modelData.separator
                            color: (barArtistMouse.containsMouse && !modelData.separator)
                                   ? Theme.accent : Theme.textTertiary
                            elide: Text.ElideRight

                            MouseArea {
                                id: barArtistMouse
                                anchors.fill: parent
                                enabled: !modelData.separator
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    if (modelData.more)
                                        barArtistMenu.popup()
                                    else
                                        control.openArtist(modelData.name)
                                }
                            }
                        }
                    }

                    ArtistMenu {
                        id: barArtistMenu
                        objectName: "playerBarArtistMenu"
                        names: ArtistNames.split(player.artist)
                        onArtistChosen: function (name) { control.openArtist(name) }
                    }

                    // 歌手与专辑之间的「 · 」独立成项：拼进专辑名里的话，悬停时
                    // 下划线会把它一起划上，看着像专辑名的一部分
                    FluText {
                        objectName: "playerBarAlbumSep"
                        Layout.alignment: Qt.AlignVCenter
                        Layout.leftMargin: 5
                        Layout.rightMargin: 5
                        visible: player.album !== "" && player.artist !== ""
                        text: "·"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                    }

                    FluText {
                        objectName: "playerBarAlbumLink"
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        visible: player.album !== ""
                        text: player.album
                        font.pixelSize: 11
                        font.underline: barAlbumMouse.containsMouse
                        color: barAlbumMouse.containsMouse ? Theme.accent : Theme.textTertiary
                        elide: Text.ElideRight

                        MouseArea {
                            id: barAlbumMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: album.openById(player.albumId, player.album)
                        }
                    }
                }

                FluText {
                    Layout.fillWidth: true
                    visible: player.artist === ""
                    text: player.title === "" ? "从「搜索」或「发现」挑一首开始" : ""
                    font.pixelSize: 11
                    color: Theme.textTertiary
                    elide: Text.ElideRight
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    visible: player.title !== ""

                    Rectangle {
                        Layout.preferredWidth: qText.implicitWidth + 12
                        Layout.preferredHeight: 16
                        radius: 8
                        color: Theme.accentSoft
                        FluText {
                            id: qText
                            anchors.centerIn: parent
                            text: player.qualityLabel
                            font.pixelSize: 9
                            color: Theme.accent
                        }
                    }

                    FluText {
                        Layout.fillWidth: true
                        text: player.sourceLabel
                        font.pixelSize: 10
                        color: Theme.textTertiary
                        elide: Text.ElideRight
                    }
                }
            }

            FluIconButton {
                Layout.preferredWidth: 32
                Layout.preferredHeight: 32
                Layout.alignment: Qt.AlignVCenter
                iconSize: 15
                iconSource: player.isFavorite ? FluentIcons.HeartFill : FluentIcons.Heart
                iconColor: player.isFavorite ? Theme.accent : Theme.textSecondary
                text: player.isFavorite ? "取消喜欢" : "我喜欢"
                visible: player.title !== ""
                onClicked: player.toggleFavorite()
            }
        }

        // ══ 中：进度 + 传输控件 ══════════════════════════
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: 12
            Layout.bottomMargin: 10
            spacing: 4

            RowLayout {
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                Layout.alignment: Qt.AlignHCenter
                spacing: 10

                FluText {
                    text: player.positionText
                    font.pixelSize: 10
                    color: Theme.textTertiary
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 40
                    horizontalAlignment: Text.AlignRight
                }

                FluSlider {
                    id: seekSlider
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignVCenter
                    from: 0
                    to: player.duration > 0 ? player.duration : 1
                    value: player.duration > 0 ? player.position : 0
                    enabled: player.duration > 0
                    tooltipEnabled: false
                    live: true

                    onMoved: {
                        if (player.duration > 0)
                            player.seek(Math.round(value))
                    }
                }

                FluText {
                    text: player.durationText
                    font.pixelSize: 10
                    color: Theme.textTertiary
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 40
                }
            }

            RowLayout {
                Layout.alignment: Qt.AlignHCenter
                spacing: 18

                // 播放模式
                FluIconButton {
                    Layout.preferredWidth: 34
                    Layout.preferredHeight: 34
                    iconSize: 15
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

                // 上一首
                FluIconButton {
                    Layout.preferredWidth: 38
                    Layout.preferredHeight: 38
                    iconSize: 18
                    iconSource: FluentIcons.Previous
                    text: "上一首"
                    onClicked: player.previous()
                }

                // 播放 / 暂停
                Rectangle {
                    Layout.preferredWidth: 42
                    Layout.preferredHeight: 42
                    radius: 21
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Theme.accent }
                        GradientStop { position: 1.0; color: Theme.accentGradientEnd }
                    }
                    scale: playMouse.pressed ? 0.93 : (playMouse.containsMouse ? 1.05 : 1.0)
                    opacity: player.loading ? 0.75 : 1.0

                    Behavior on scale { NumberAnimation { duration: Theme.durationFast } }

                    FluProgressRing {
                        anchors.centerIn: parent
                        width: 22
                        height: 22
                        strokeWidth: 2
                        color: Theme.accentText
                        visible: player.loading
                    }

                    FluIcon {
                        anchors.centerIn: parent
                        visible: !player.loading
                        iconSource: player.playing ? FluentIcons.Pause : FluentIcons.PlaySolid
                        iconSize: 16
                        iconColor: Theme.accentText
                    }

                    FluTooltip {
                        visible: playMouse.containsMouse
                        text: player.playing ? "暂停" : "播放"
                        delay: 400
                    }

                    MouseArea {
                        id: playMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: player.toggle()
                    }
                }

                // 下一首
                FluIconButton {
                    Layout.preferredWidth: 38
                    Layout.preferredHeight: 38
                    iconSize: 18
                    iconSource: FluentIcons.Next
                    text: "下一首"
                    onClicked: player.next()
                }

                // 歌词 / 展开
                FluIconButton {
                    Layout.preferredWidth: 34
                    Layout.preferredHeight: 34
                    iconSize: 15
                    iconSource: FluentIcons.MusicInfo
                    iconColor: player.hasLyrics ? Theme.accent : Theme.textSecondary
                    text: "歌词"
                    enabled: control.canExpand
                    onClicked: control.openNowPlaying()
                }
            }
        }

        // ══ 右：音量 / 队列 / 展开 ═══════════════════════
        RowLayout {
            Layout.preferredWidth: 300
            Layout.minimumWidth: 190
            Layout.fillHeight: true
            spacing: 6

            Item { Layout.fillWidth: true }

            // 队列
            FluIconButton {
                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                Layout.alignment: Qt.AlignVCenter
                iconSize: 15
                iconSource: FluentIcons.List
                iconColor: app.queuePanel ? Theme.accent : Theme.textSecondary
                text: "播放队列（" + player.queueCount + "）"
                onClicked: app.toggleQueuePanel()
            }

            // 音量
            FluIconButton {
                Layout.preferredWidth: 30
                Layout.preferredHeight: 34
                Layout.alignment: Qt.AlignVCenter
                iconSize: 15
                iconSource: {
                    if (player.muted || player.volume === 0) return FluentIcons.Volume0
                    if (player.volume < 34) return FluentIcons.Volume0
                    if (player.volume < 67) return FluentIcons.Volume1
                    return FluentIcons.Volume2
                }
                iconColor: player.muted ? Theme.textTertiary : Theme.textSecondary
                text: player.muted ? "取消静音" : "静音"
                onClicked: player.toggleMute()
            }

            FluSlider {
                Layout.preferredWidth: 84
                Layout.alignment: Qt.AlignVCenter
                from: 0
                to: 100
                value: player.muted ? 0 : player.volume
                tooltipEnabled: true
                text: Math.round(value) + "%"
                visible: control.width > 900
                onMoved: player.setVolume(Math.round(value))
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 22
                Layout.alignment: Qt.AlignVCenter
                Layout.leftMargin: 4
                Layout.rightMargin: 2
                color: Theme.border
                visible: control.canExpand
            }

            // 展开 / 收起（草图右下角的 ^）
            FluIconButton {
                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                Layout.alignment: Qt.AlignVCenter
                iconSize: 16
                iconSource: control.expanded ? FluentIcons.ChevronDown : FluentIcons.ChevronUp
                iconColor: control.expanded ? Theme.accent : Theme.textSecondary
                text: control.expanded ? "收起" : "展开播放页"
                visible: control.canExpand
                onClicked: control.expandToggled()
            }
        }
    }

    // 封面「另存为」（见 components/CoverSaveDialog.qml）
    CoverSaveDialog {
        id: coverSaveDialog
    }
}
