import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    专辑详情覆盖层：封面 / 专辑名 / 歌手 / 发行信息 + 曲目列表。

    数据来自 ``AlbumController``（点任意地方的专辑名都会打开它）。
    版式参照网易云的专辑页，但只做「歌曲」这一页 —— 评论 / 专辑详情这些
    需要评论接口与富文本，暂不做。
*/
Item {
    id: control

    objectName: "albumDetailPanel"

    signal closeRequested

    readonly property var meta: album.meta

    // 歌手（可点，进歌手页）
    readonly property var artistNames: {
        var list = meta.artists !== undefined && meta.artists !== null ? meta.artists : []
        return list
    }

    // 「2025-04-01 发布」这一行
    readonly property string subtitle: {
        if (meta.publish_text !== undefined && meta.publish_text !== "")
            return meta.publish_text + " 发布"
        return ""
    }

    // 「单曲 · 旧时约定 · 2 首」
    readonly property string statsText: {
        var parts = []
        if (meta.type_text !== undefined && meta.type_text !== "")
            parts.push(meta.type_text)
        if (meta.company !== undefined && meta.company !== "")
            parts.push(meta.company)
        if (album.model.count > 0)
            parts.push(album.model.count + " 首")
        return parts.join("  ·  ")
    }

    // ── 事件遮罩 ────────────────────────────────────────
    // 和其它覆盖层同一个坑：普通 Item 的空白处不吃鼠标事件，会点穿到底下的
    // 导航栏 / 页面。必须声明在其它子项之前，可交互控件才仍然优先拿到事件。
    MouseArea {
        objectName: "albumDetailBlocker"
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onWheel: function (wheel) { wheel.accepted = true }
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.windowBg
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        // ── 顶部返回 ────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            FluIconButton {
                objectName: "albumBackButton"
                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                Layout.alignment: Qt.AlignVCenter
                iconSize: 15
                iconSource: FluentIcons.ChevronLeft
                iconColor: Theme.textSecondary
                text: "返回"
                onClicked: control.closeRequested()
            }

            FluText {
                Layout.alignment: Qt.AlignVCenter
                text: "专辑"
                font.pixelSize: 12
                color: Theme.textSecondary
            }

            Item { Layout.fillWidth: true }

            FluProgressRing {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                Layout.alignment: Qt.AlignVCenter
                strokeWidth: 3
                visible: album.loading
            }
        }

        // ── 专辑信息头 ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 20

            Rectangle {
                Layout.preferredWidth: 148
                Layout.preferredHeight: 148
                Layout.alignment: Qt.AlignTop
                radius: Theme.radiusLarge
                color: Theme.cardBg
                border.width: 1
                border.color: Theme.border
                clip: true

                Image {
                    anchors.fill: parent
                    source: meta.cover !== undefined ? meta.cover : ""
                    visible: source !== ""
                    fillMode: Image.PreserveAspectCrop
                    sourceSize.width: 296
                    sourceSize.height: 296
                }

                FluIcon {
                    anchors.centerIn: parent
                    visible: !(meta.cover !== undefined && meta.cover !== "")
                    iconSource: FluentIcons.MusicNote
                    iconSize: 44
                    iconColor: Theme.dark ? "#3A3846" : "#CFCCE0"
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 8

                FluText {
                    Layout.fillWidth: true
                    text: meta.name !== undefined && meta.name !== ""
                        ? meta.name
                        : (album.loading ? "正在查找专辑…" : "专辑")
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                // 歌手名可点（进歌手页）
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    visible: control.artistNames.length > 0

                    Repeater {
                        model: control.artistNames
                        delegate: FluText {
                            required property var modelData
                            required property int index

                            objectName: "albumArtistLink"
                            Layout.alignment: Qt.AlignVCenter
                            Layout.maximumWidth: 220
                            text: (index > 0 ? " / " : "") + modelData.name
                            font.pixelSize: 13
                            font.underline: albumArtistMouse.containsMouse
                            color: albumArtistMouse.containsMouse ? Theme.accent : Theme.textSecondary
                            elide: Text.ElideRight

                            MouseArea {
                                id: albumArtistMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: artist.openById(modelData.id, modelData.name)
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                FluText {
                    Layout.fillWidth: true
                    visible: text !== ""
                    text: control.subtitle
                    font.pixelSize: 12
                    color: Theme.textTertiary
                    elide: Text.ElideRight
                }

                FluText {
                    Layout.fillWidth: true
                    visible: text !== ""
                    text: control.statsText
                    font.pixelSize: 12
                    color: Theme.textTertiary
                    elide: Text.ElideRight
                }

                FluText {
                    Layout.fillWidth: true
                    Layout.maximumHeight: 44
                    visible: text !== ""
                    text: meta.description !== undefined ? meta.description : ""
                    font.pixelSize: 11
                    color: Theme.textTertiary
                    wrapMode: Text.WordWrap
                    elide: Text.ElideRight
                    maximumLineCount: 2
                }

                RowLayout {
                    Layout.topMargin: 6
                    spacing: 10

                    FluFilledButton {
                        objectName: "albumPlayAllButton"
                        text: "播放全部"
                        disabled: album.model.count === 0
                        onClicked: player.playTrackInList(album.model.allItems(), 0)
                    }

                    FluButton {
                        text: "添加到队列"
                        disabled: album.model.count === 0
                        onClicked: player.extendQueue(album.model.allItems())
                    }

                    FluButton {
                        text: "全部收藏"
                        disabled: album.model.count === 0
                        onClicked: library.addManyToFavorites(album.model.allItems())
                    }
                }
            }
        }

        // ── 曲目 ────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            FluText {
                text: "歌曲"
                font.pixelSize: 15
                font.weight: Font.DemiBold
                color: Theme.textPrimary
            }

            FluText {
                Layout.alignment: Qt.AlignVCenter
                visible: album.model.count > 0
                text: String(album.model.count) + " 首"
                font.pixelSize: 11
                color: Theme.textTertiary
            }

            Item { Layout.fillWidth: true }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border
            clip: true

            TrackListView {
                anchors.fill: parent
                anchors.margins: 6
                model: album.model
                showCover: false
                showAlbum: false
                busy: album.loading
                emptyIcon: FluentIcons.MusicNote
                emptyTitle: album.loading ? "正在加载专辑…" : "这张专辑没有可播放的歌曲"
                emptyDescription: album.loading ? "" : "网易云接口里没有可播放的曲目，换一张专辑试试"
                onTrackActivated: function (index) {
                    player.playTrackInList(album.model.allItems(), index)
                }
                onRequestPlayNow: function (track) { player.playTrack(track) }
                onRequestPlayNext: function (track) { player.playNextTrack(track) }
                onRequestAppend: function (track) { player.appendToQueue(track) }
                onRequestFavorite: function (track) { library.toggleFavorite(track) }
            }
        }
    }
}
