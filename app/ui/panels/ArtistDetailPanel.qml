import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"
import "../ArtistNames.js" as ArtistNames

/*!
    歌手详情覆盖层：头像 / 数据 / 简介 + 热门歌曲。

    数据来自 ``ArtistController``（点任意地方的歌手名都会打开它）。
    版式参照网易云的歌手页，但只保留真正接得上的部分：热门歌曲、播放全部。
    专辑 / MV / 相似歌手没有做（需要额外的详情页承接，另开一轮再说）。
*/
Item {
    id: control

    objectName: "artistDetailPanel"

    signal closeRequested

    readonly property var meta: artist.meta

    // 别名 / 单曲·专辑·MV·粉丝，都在这里拼好，界面上直接显示
    readonly property string aliasText: {
        var alias = meta.alias !== undefined && meta.alias !== null ? meta.alias : []
        return alias.length > 0 ? "别名：" + alias.join(" / ") : ""
    }

    readonly property string statsText: {
        var parts = []
        if (meta.music_size !== undefined && meta.music_size > 0)
            parts.push("单曲 " + meta.music_size)
        if (meta.album_size !== undefined && meta.album_size > 0)
            parts.push("专辑 " + meta.album_size)
        if (meta.mv_size !== undefined && meta.mv_size > 0)
            parts.push("MV " + meta.mv_size)
        if (meta.fans_size !== undefined && meta.fans_size > 0)
            parts.push("粉丝 " + ArtistNames.formatCount(meta.fans_size))
        return parts.join("  ·  ")
    }

    // ── 事件遮罩 ────────────────────────────────────────
    // 和其它覆盖层同一个坑：普通 Item 的空白处不吃鼠标事件，会点穿到底下的
    // 导航栏 / 页面。必须声明在其它子项之前，可交互控件才仍然优先拿到事件。
    MouseArea {
        objectName: "artistDetailBlocker"
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
                objectName: "artistBackButton"
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
                text: "歌手"
                font.pixelSize: 12
                color: Theme.textSecondary
            }

            Item { Layout.fillWidth: true }

            FluProgressRing {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                Layout.alignment: Qt.AlignVCenter
                strokeWidth: 3
                visible: artist.loading
            }
        }

        // ── 歌手信息头 ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 20

            // 圆形头像
            Rectangle {
                Layout.preferredWidth: 132
                Layout.preferredHeight: 132
                Layout.alignment: Qt.AlignTop
                radius: 66
                color: Theme.cardBg
                border.width: 1
                border.color: Theme.border
                clip: true

                Image {
                    anchors.fill: parent
                    source: artist.meta.cover !== undefined ? artist.meta.cover : ""
                    visible: source !== ""
                    fillMode: Image.PreserveAspectCrop
                    sourceSize.width: 264
                    sourceSize.height: 264
                }

                FluIcon {
                    anchors.centerIn: parent
                    visible: !(artist.meta.cover !== undefined && artist.meta.cover !== "")
                    iconSource: FluentIcons.Contact
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
                    text: artist.meta.name !== undefined && artist.meta.name !== ""
                        ? artist.meta.name
                        : (artist.loading ? "正在查找歌手…" : "歌手")
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                    elide: Text.ElideRight
                }

                // 别名 / 组合名
                FluText {
                    Layout.fillWidth: true
                    visible: control.aliasText !== ""
                    text: control.aliasText
                    font.pixelSize: 12
                    color: Theme.textSecondary
                    elide: Text.ElideRight
                }

                // 单曲 / 专辑 / MV / 粉丝
                FluText {
                    Layout.fillWidth: true
                    visible: control.statsText !== ""
                    text: control.statsText
                    font.pixelSize: 12
                    color: Theme.textTertiary
                    elide: Text.ElideRight
                }

                FluText {
                    Layout.fillWidth: true
                    Layout.maximumHeight: 44
                    visible: text !== ""
                    text: artist.meta.brief_desc !== undefined ? artist.meta.brief_desc : ""
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
                        objectName: "artistPlayAllButton"
                        text: "播放全部"
                        disabled: artist.hotModel.count === 0
                        onClicked: player.playTrackInList(artist.hotModel.allItems(), 0)
                    }

                    FluButton {
                        text: "添加到队列"
                        disabled: artist.hotModel.count === 0
                        onClicked: player.extendQueue(artist.hotModel.allItems())
                    }

                    FluButton {
                        text: "全部收藏"
                        disabled: artist.hotModel.count === 0
                        onClicked: library.addManyToFavorites(artist.hotModel.allItems())
                    }
                }
            }
        }

        // ── 热门歌曲 ────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            FluText {
                text: "热门歌曲"
                font.pixelSize: 15
                font.weight: Font.DemiBold
                color: Theme.textPrimary
            }

            FluText {
                Layout.alignment: Qt.AlignVCenter
                visible: artist.hotModel.count > 0
                text: String(artist.hotModel.count) + " 首"
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
                model: artist.hotModel
                showCover: false
                busy: artist.loading
                emptyIcon: FluentIcons.Contact
                emptyTitle: artist.loading ? "正在加载歌手…" : "没有找到这位歌手的热门歌曲"
                emptyDescription: artist.loading ? "" : "网易云接口里没有可播放的歌曲，换个歌手试试"
                onTrackActivated: function (index) {
                    player.playTrackInList(artist.hotModel.allItems(), index)
                }
                onRequestPlayNow: function (track) { player.playTrack(track) }
                onRequestPlayNext: function (track) { player.playNextTrack(track) }
                onRequestAppend: function (track) { player.appendToQueue(track) }
                onRequestFavorite: function (track) { library.toggleFavorite(track) }
            }
        }
    }
}
