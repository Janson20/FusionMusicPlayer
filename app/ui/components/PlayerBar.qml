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

    property bool expanded: false
    property bool canExpand: true

    signal expandToggled
    signal openNowPlaying

    // 点歌手名进歌手页（只取第一位，这里放不下多个名字）
    function openArtist(text) {
        var name = ArtistNames.first(text)
        if (name !== "")
            artist.openByName(name)
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
                    opacity: coverMouse.containsMouse ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
                    FluIcon {
                        anchors.centerIn: parent
                        iconSource: FluentIcons.ChevronUp
                        iconSize: 18
                        iconColor: "#FFFFFF"
                    }
                }

                MouseArea {
                    id: coverMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    enabled: control.canExpand
                    onClicked: control.openNowPlaying()
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 4

                FluText {
                    Layout.fillWidth: true
                    text: player.title !== "" ? player.title : "未在播放"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    color: player.title !== "" ? Theme.textPrimary : Theme.textTertiary
                    elide: Text.ElideRight
                }

                // 歌手名可点（进歌手页），专辑名跟在后面
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    visible: player.artist !== ""

                    FluText {
                        objectName: "playerBarArtistLink"
                        Layout.maximumWidth: 200
                        Layout.alignment: Qt.AlignVCenter
                        text: player.artist
                        font.pixelSize: 11
                        font.underline: barArtistMouse.containsMouse
                        color: barArtistMouse.containsMouse ? Theme.accent : Theme.textTertiary
                        elide: Text.ElideRight

                        MouseArea {
                            id: barArtistMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: control.openArtist(player.artist)
                        }
                    }

                    FluText {
                        objectName: "playerBarAlbumLink"
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        visible: player.album !== ""
                        text: (player.artist !== "" ? "  ·  " : "") + player.album
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
}
