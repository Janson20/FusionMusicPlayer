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

    OverlayBackdrop {
        anchors.fill: parent
        blockerObjectName: "artistDetailBlocker"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16
        DetailBackBar {
            title: "歌手"
            loading: artist.loading
            backObjectName: "artistBackButton"
            onBackRequested: control.closeRequested()
        }

        // ── 歌手信息头 ──────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 20

            // 圆形头像
            // 圆形头像：CoverArt 的 circle 模式（占位图标换成联系人）
            CoverArt {
                Layout.preferredWidth: 132
                Layout.preferredHeight: 132
                Layout.alignment: Qt.AlignTop
                circle: true
                borderWidth: 1
                borderColor: Theme.border
                placeholderIcon: FluentIcons.Contact
                source: artist.meta.cover !== undefined ? artist.meta.cover : ""
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
                        disabled: artist.model.count === 0
                        onClicked: player.playTrackInList(artist.model.allItems(), 0)
                    }

                    FluButton {
                        text: "添加到队列"
                        disabled: artist.model.count === 0
                        onClicked: player.extendQueue(artist.model.allItems())
                    }

                    FluButton {
                        text: "全部收藏"
                        disabled: artist.model.count === 0
                        onClicked: library.addManyToFavorites(artist.model.allItems())
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
                visible: artist.model.count > 0
                text: String(artist.model.count) + " 首"
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
                model: artist.model
                showCover: false
                busy: artist.loading
                selectable: true
                emptyIcon: FluentIcons.Contact
                emptyTitle: artist.loading ? "正在加载歌手…" : "没有找到这位歌手的热门歌曲"
                emptyDescription: artist.loading ? "" : "网易云接口里没有可播放的歌曲，换个歌手试试"
            }
        }
    }
}
