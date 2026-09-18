import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    发现页：推荐歌单 / 排行榜 / 最新音乐 / 每日推荐。
*/
Item {
    id: control

    readonly property int cardWidth: 154
    readonly property int gridColumns: Math.max(2, Math.floor((width - 48) / (cardWidth + 14)))

    function playAll(model, startIndex) {
        if (!model || model.count === 0)
            return
        player.playTrackInList(model.allItems(), startIndex)
    }

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.height + 40
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        ScrollBar.vertical: FluScrollBar { }

        ColumnLayout {
            id: contentColumn
            width: flick.width - 48
            x: 24
            y: 20
            spacing: 26

            // ── 顶部问候 ────────────────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: 14

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    FluText {
                        text: {
                            var h = new Date().getHours()
                            var greet = h < 6 ? "夜深了" : (h < 12 ? "早上好" : (h < 18 ? "下午好" : "晚上好"))
                            return greet + (account.loggedIn ? "，" + (account.nickname || "") : "")
                        }
                        font.pixelSize: 22
                        font.weight: Font.Bold
                        color: Theme.textPrimary
                    }
                    FluText {
                        text: account.loggedIn
                            ? "已连接网易云音乐 · " + account.vipLabel
                            : "登录网易云可解锁无损音质、歌单同步与每日推荐"
                        font.pixelSize: 12
                        color: Theme.textTertiary
                    }
                }

                FluButton {
                    Layout.alignment: Qt.AlignVCenter
                    visible: !account.loggedIn
                    text: "登录网易云"
                    onClicked: app.openLogin()
                }

                FluIconButton {
                    Layout.alignment: Qt.AlignVCenter
                    Layout.preferredWidth: 34
                    Layout.preferredHeight: 34
                    iconSize: 15
                    iconSource: FluentIcons.Refresh
                    iconColor: Theme.textSecondary
                    text: "刷新"
                    onClicked: discover.reload()
                }
            }

            // ── 每日推荐（登录后）───────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10
                visible: discover.hasDaily

                SectionHeader {
                    Layout.fillWidth: true
                    title: "每日推荐"
                    subtitle: "根据你的口味生成"
                    actionText: "播放全部"
                    onActionTriggered: control.playAll(discover.dailyModel, 0)
                }

                TrackListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(300, discover.dailyModel.count * 54 + 4)
                    model: discover.dailyModel
                    emptyTitle: "暂无每日推荐"
                    onTrackActivated: function (index) {
                        player.playTrackInList(discover.dailyModel.allItems(), index)
                    }
                    onRequestPlayNow: function (track) { player.playTrack(track) }
                    onRequestPlayNext: function (track) { player.playNextTrack(track) }
                    onRequestAppend: function (track) { player.appendToQueue(track) }
                    onRequestFavorite: function (track) { library.toggleFavorite(track) }
                }
            }

            // ── 推荐歌单 ────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10
                visible: discover.recommendPlaylists.length > 0

                SectionHeader {
                    Layout.fillWidth: true
                    title: "推荐歌单"
                    subtitle: "网易云编辑精选"
                }

                GridView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(2, Math.ceil(discover.recommendPlaylists.length / control.gridColumns))
                                            * (control.cardWidth + 54) + 12
                    cellWidth: control.cardWidth + 14
                    cellHeight: control.cardWidth + 54 + 14
                    interactive: false
                    clip: true
                    model: discover.recommendPlaylists

                    delegate: PlaylistCard {
                        required property var modelData
                        width: control.cardWidth
                        title: modelData.name
                        cover: modelData.cover
                        subtitle: modelData.play_count > 0
                            ? (modelData.play_count >= 10000
                                ? (modelData.play_count / 10000).toFixed(1) + "万"
                                : String(modelData.play_count))
                            : ""
                        trackCount: modelData.track_count
                        onActivated: discover.openPlaylist(modelData.id, modelData.name)
                        onPlayRequested: discover.openPlaylist(modelData.id, modelData.name)
                    }
                }
            }

            // ── 排行榜 ──────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10
                visible: discover.toplists.length > 0

                SectionHeader {
                    Layout.fillWidth: true
                    title: "排行榜"
                    subtitle: "官方榜单实时更新"
                }

                GridView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(2, Math.ceil(discover.toplists.length / control.gridColumns))
                                            * (control.cardWidth + 54) + 12
                    cellWidth: control.cardWidth + 14
                    cellHeight: control.cardWidth + 54 + 14
                    interactive: false
                    clip: true
                    model: discover.toplists

                    delegate: PlaylistCard {
                        required property var modelData
                        width: control.cardWidth
                        title: modelData.name
                        cover: modelData.cover
                        subtitle: modelData.update_frequency
                        trackCount: modelData.track_count
                        onActivated: discover.openPlaylist(modelData.id, modelData.name)
                        onPlayRequested: discover.openPlaylist(modelData.id, modelData.name)
                    }
                }
            }

            // ── 最新音乐 ────────────────────────────────────
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 10
                visible: discover.newSongsModel.count > 0

                SectionHeader {
                    Layout.fillWidth: true
                    title: "最新音乐"
                    actionText: "播放全部"
                    onActionTriggered: control.playAll(discover.newSongsModel, 0)
                }

                TrackListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.min(420, discover.newSongsModel.count * 54 + 4)
                    model: discover.newSongsModel
                    onTrackActivated: function (index) {
                        player.playTrackInList(discover.newSongsModel.allItems(), index)
                    }
                    onRequestPlayNow: function (track) { player.playTrack(track) }
                    onRequestPlayNext: function (track) { player.playNextTrack(track) }
                    onRequestAppend: function (track) { player.appendToQueue(track) }
                    onRequestFavorite: function (track) { library.toggleFavorite(track) }
                }
            }

            // ── 加载 / 空状态 ───────────────────────────────
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 200
                visible: discover.loading || (discover.recommendPlaylists.length === 0 && discover.toplists.length === 0)

                EmptyState {
                    anchors.fill: parent
                    busy: discover.loading
                    iconSource: FluentIcons.Globe
                    title: discover.loading ? "正在加载发现页…" : "发现页暂时没有内容"
                    description: discover.loading ? "" : "检查网络连接后点击重试"
                    actionText: discover.loading ? "" : "重新加载"
                    onActionTriggered: discover.reload()
                }
            }

            Item { Layout.preferredHeight: 20 }
        }
    }
}
