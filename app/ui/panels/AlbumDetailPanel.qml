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

    OverlayBackdrop {
        anchors.fill: parent
        blockerObjectName: "albumDetailBlocker"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        DetailBackBar {
            title: "专辑"
            loading: album.loading
            backObjectName: "albumBackButton"
            onBackRequested: control.closeRequested()
        }

        // ── 专辑信息头 ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 20

            // 大封面：与列表 / 歌单页共用 CoverArt（描边由它自己画）
            CoverArt {
                Layout.preferredWidth: 148
                Layout.preferredHeight: 148
                Layout.alignment: Qt.AlignTop
                radiusSize: Theme.radiusLarge
                borderWidth: 1
                borderColor: Theme.border
                source: meta.cover !== undefined ? meta.cover : ""
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

                // 歌手名可点（进歌手页）。合辑能挂十几个歌手，同样只铺开前几位，
                // 其余收进「等 N 人」——这一行是不会换行的 RowLayout，
                // 撑开之后会横着盖住右边的专辑信息。
                // 外层 Item 把宽度夹在可用范围内：放得下就自然排，放不下才逐项省略
                // （只给子项 fillWidth 的话，多出来的宽度会被分给歌手名，
                //   名字之间被拉出大段空白，反而不像一行）
                ArtistLinkRow {
                    Layout.fillWidth: true
                    Layout.preferredHeight: implicitHeight
                    entries: true
                    source: control.artistNames
                    pixelSize: 13
                    normalColor: Theme.textSecondary
                    linkMinWidth: 36
                    linkMaxWidth: 220
                    moreMaxWidth: 220
                    objectPrefix: "albumArtist"
                    onArtistActivated: function (id, name) { artist.openById(id, name) }
                    onArtistChosen: function (name) { artist.openByName(name) }
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

        CardPanel {
            Layout.fillWidth: true
            Layout.fillHeight: true

            TrackListView {
                anchors.fill: parent
                anchors.margins: 6
                model: album.model
                showCover: false
                showAlbum: false
                busy: album.loading
                selectable: true
                emptyIcon: FluentIcons.MusicNote
                emptyTitle: album.loading ? "正在加载专辑…" : "这张专辑没有可播放的歌曲"
                emptyDescription: album.loading ? "" : "网易云接口里没有可播放的曲目，换一张专辑试试"
            }
        }
    }
}
