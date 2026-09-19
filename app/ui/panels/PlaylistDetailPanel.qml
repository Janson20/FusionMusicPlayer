import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    歌单详情覆盖层：从发现页点开推荐歌单 / 排行榜后展示完整曲目。
*/
Item {
    id: control

    signal closeRequested

    // ── 事件遮罩 ────────────────────────────────────────
    // 和展开播放页同一个坑：普通 Item 的空白处不处理鼠标事件，点击会穿到
    // 底下的导航栏 / 页面（点名「返回发现页」旁边的空白会直接切页）。
    // 必须声明在其它子项之前，可交互控件才仍然优先拿到事件。
    MouseArea {
        objectName: "playlistDetailBlocker"
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
                objectName: "detailBackButton"
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
                text: "返回发现页"
                font.pixelSize: 12
                color: Theme.textSecondary
            }

            Item { Layout.fillWidth: true }

            FluProgressRing {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                Layout.alignment: Qt.AlignVCenter
                strokeWidth: 3
                visible: discover.detailLoading
            }
        }

        // ── 歌单信息头 ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 20

            CoverArt {
                Layout.preferredWidth: 148
                Layout.preferredHeight: 148
                Layout.alignment: Qt.AlignTop
                radiusSize: Theme.radiusLarge
                source: discover.detailMeta.cover !== undefined ? discover.detailMeta.cover : ""
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 8

                FluText {
                    Layout.fillWidth: true
                    text: discover.detailMeta.name !== undefined && discover.detailMeta.name !== ""
                        ? discover.detailMeta.name : "歌单"
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    color: Theme.textPrimary
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }

                FluText {
                    Layout.fillWidth: true
                    visible: discover.detailMeta.creator !== undefined && discover.detailMeta.creator !== ""
                    text: "by " + (discover.detailMeta.creator !== undefined ? discover.detailMeta.creator : "")
                    font.pixelSize: 12
                    color: Theme.textSecondary
                }

                FluText {
                    Layout.fillWidth: true
                    text: discover.detailModel.count + " 首歌曲"
                    font.pixelSize: 12
                    color: Theme.textTertiary
                }

                FluText {
                    Layout.fillWidth: true
                    Layout.maximumHeight: 44
                    visible: discover.detailMeta.description !== undefined && discover.detailMeta.description !== ""
                    text: discover.detailMeta.description !== undefined ? discover.detailMeta.description : ""
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
                        text: "播放全部"
                        disabled: discover.detailModel.count === 0
                        onClicked: player.playTrackInList(discover.detailModel.allItems(), 0)
                    }

                    FluButton {
                        text: "添加到队列"
                        disabled: discover.detailModel.count === 0
                        onClicked: player.extendQueue(discover.detailModel.allItems())
                    }

                    FluButton {
                        text: "全部收藏"
                        disabled: discover.detailModel.count === 0
                        onClicked: library.addManyToFavorites(discover.detailModel.allItems())
                    }
                }
            }
        }

        // ── 曲目 ────────────────────────────────────────────
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
                model: discover.detailModel
                showCover: false
                busy: discover.detailLoading
                emptyIcon: FluentIcons.Library
                emptyTitle: discover.detailLoading ? "正在加载歌单…" : "这个歌单没有可播放的歌曲"
                emptyDescription: "部分歌单需要登录网易云后才能读取"
                onTrackActivated: function (index) {
                    player.playTrackInList(discover.detailModel.allItems(), index)
                }
                onRequestPlayNow: function (track) { player.playTrack(track) }
                onRequestPlayNext: function (track) { player.playNextTrack(track) }
                onRequestAppend: function (track) { player.appendToQueue(track) }
                onRequestFavorite: function (track) { library.toggleFavorite(track) }
            }
        }
    }
}
