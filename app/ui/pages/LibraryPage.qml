import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    我的音乐：左侧歌单列表（我喜欢的音乐 / 最近播放 / 自建歌单），右侧曲目。
*/
Item {
    id: control

    property int pendingDeleteIndex: -1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 18

        // ══ 左：歌单列表 ═════════════════════════════════
        Rectangle {
            Layout.preferredWidth: 236
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 10
                spacing: 8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    FluText {
                        text: "我的歌单"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                        Layout.fillWidth: true
                    }

                    FluIconButton {
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 28
                        iconSize: 14
                        iconSource: FluentIcons.Add
                        iconColor: Theme.accent
                        text: "新建歌单"
                        onClicked: createDialog.openWith("")
                    }
                }

                ListView {
                    id: playlistList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 2
                    model: library.playlists
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: FluScrollBar { }

                    header: Item { width: 1; height: 2 }

                    delegate: Rectangle {
                        id: plDelegate
                        required property var modelData
                        width: playlistList.width
                        height: 46
                        radius: Theme.radiusSmall
                        color: library.selectedId === modelData.id
                            ? Theme.accentSoft
                            : (plMouse.containsMouse ? Theme.cardHover : "transparent")
                        Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 6
                            spacing: 10

                            Rectangle {
                                Layout.preferredWidth: 28
                                Layout.preferredHeight: 28
                                Layout.alignment: Qt.AlignVCenter
                                radius: Theme.radiusSmall
                                color: library.selectedId === modelData.id
                                    ? Theme.accent : (Theme.dark ? "#2C2A38" : "#F0EFF7")
                                FluIcon {
                                    anchors.centerIn: parent
                                    iconSource: modelData.icon === "Heart" ? FluentIcons.Heart
                                        : (modelData.icon === "History" ? FluentIcons.History
                                        : (modelData.icon === "Folder" ? FluentIcons.Folder
                                        : FluentIcons.List))
                                    iconSize: 13
                                    iconColor: library.selectedId === modelData.id
                                        ? Theme.accentText : Theme.textSecondary
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                FluText {
                                    Layout.fillWidth: true
                                    text: modelData.name
                                    font.pixelSize: 12
                                    font.weight: library.selectedId === modelData.id ? Font.DemiBold : Font.Normal
                                    color: library.selectedId === modelData.id ? Theme.accent : Theme.textPrimary
                                    elide: Text.ElideRight
                                }
                                FluText {
                                    text: modelData.count + " 首"
                                    font.pixelSize: 10
                                    color: Theme.textTertiary
                                }
                            }

                            FluIconButton {
                                Layout.preferredWidth: 26
                                Layout.preferredHeight: 26
                                iconSize: 13
                                iconSource: FluentIcons.More
                                iconColor: Theme.textSecondary
                                text: "更多"
                                visible: !modelData.system || modelData.id === "__favorites__"
                                opacity: plMouse.containsMouse ? 1 : 0
                                onClicked: {
                                    plMenu.targetId = modelData.id
                                    plMenu.targetName = modelData.name
                                    plMenu.targetSystem = modelData.system
                                    plMenu.popup()
                                }
                            }
                        }

                        MouseArea {
                            id: plMouse
                            anchors.fill: parent
                            anchors.rightMargin: 30
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: library.select(modelData.id)
                        }
                    }

                    footer: ColumnLayout {
                        width: playlistList.width
                        spacing: 2

                        // ── 网易云歌单 ──────────────────────
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.topMargin: 12
                            Layout.leftMargin: 4
                            Layout.rightMargin: 4
                            Layout.bottomMargin: 4
                            spacing: 6

                            FluText {
                                Layout.fillWidth: true
                                text: account.loggedIn ? "网易云歌单" : ""
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                                color: Theme.textTertiary
                                visible: account.loggedIn
                            }
                            FluProgressRing {
                                Layout.preferredWidth: 13
                                Layout.preferredHeight: 13
                                Layout.alignment: Qt.AlignVCenter
                                strokeWidth: 2
                                visible: library.remoteLoading
                            }
                            FluIconButton {
                                Layout.preferredWidth: 22
                                Layout.preferredHeight: 22
                                iconSize: 12
                                iconSource: FluentIcons.Sync
                                iconColor: Theme.textTertiary
                                text: "重新同步歌单"
                                visible: account.loggedIn
                                onClicked: account.syncPlaylists()
                            }
                        }

                        // 未登录时的引导
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 40
                            visible: !account.loggedIn
                            radius: Theme.radiusSmall
                            color: loginMouse.containsMouse ? Theme.accentSoft : "transparent"

                            FluText {
                                anchors.centerIn: parent
                                text: "登录网易云同步歌单"
                                font.pixelSize: 11
                                color: Theme.accent
                            }
                            MouseArea {
                                id: loginMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: app.openLogin()
                            }
                        }

                        Repeater {
                            model: library.remotePlaylists
                            delegate: Rectangle {
                                id: remoteDelegate
                                required property var modelData
                                Layout.fillWidth: true
                                Layout.preferredHeight: 46
                                radius: Theme.radiusSmall
                                color: library.selectedId === ("wy:" + modelData.id)
                                    ? Theme.accentSoft
                                    : (remoteMouse.containsMouse ? Theme.cardHover : "transparent")
                                Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                                readonly property bool active: library.selectedId === ("wy:" + modelData.id)

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 8
                                    anchors.rightMargin: 8
                                    spacing: 10

                                    Item {
                                        Layout.preferredWidth: 28
                                        Layout.preferredHeight: 28
                                        Layout.alignment: Qt.AlignVCenter

                                        CoverArt {
                                            anchors.fill: parent
                                            radiusSize: Theme.radiusSmall
                                            source: modelData.cover
                                        }
                                        FluIcon {
                                            anchors.centerIn: parent
                                            visible: modelData.cover === ""
                                            iconSource: FluentIcons.Cloud
                                            iconSize: 13
                                            iconColor: remoteDelegate.active
                                                ? Theme.accentText : Theme.textSecondary
                                        }
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 1
                                        FluText {
                                            Layout.fillWidth: true
                                            text: modelData.name
                                            font.pixelSize: 12
                                            font.weight: remoteDelegate.active ? Font.DemiBold : Font.Normal
                                            color: remoteDelegate.active ? Theme.accent : Theme.textPrimary
                                            elide: Text.ElideRight
                                        }
                                        FluText {
                                            text: modelData.count + " 首"
                                            font.pixelSize: 10
                                            color: Theme.textTertiary
                                        }
                                    }
                                }

                                MouseArea {
                                    id: remoteMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: library.selectRemote(modelData.id, modelData.name)
                                }
                            }
                        }

                        FluText {
                            Layout.fillWidth: true
                            Layout.topMargin: 4
                            Layout.leftMargin: 6
                            Layout.rightMargin: 6
                            visible: account.loggedIn && library.remotePlaylists.length === 0
                            text: "还没有同步到歌单"
                            font.pixelSize: 10
                            color: Theme.textTertiary
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                FluText {
                    Layout.fillWidth: true
                    visible: library.playlists.length === 0
                    text: "还没有歌单，点右上角 + 新建"
                    font.pixelSize: 11
                    color: Theme.textTertiary
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }

        // ══ 右：曲目列表 ═════════════════════════════════
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            SectionHeader {
                Layout.fillWidth: true
                title: library.selectedName !== "" ? library.selectedName : "请选择歌单"
                subtitle: library.selectedCount + " 首"
                actionText: library.selectedCount > 0 ? "播放全部" : ""
                onActionTriggered: player.playTrackInList(library.tracksModel.allItems(), 0)
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
                    model: library.tracksModel
                    busy: library.selectedIsRemote && library.remoteLoading
                    emptyIcon: library.selectedIsRemote ? FluentIcons.Cloud : FluentIcons.Heart
                    emptyTitle: library.selectedIsRemote
                        ? (library.remoteLoading ? "正在同步歌单…" : "这个歌单没有可显示的歌曲")
                        : (library.selectedId === "__history__"
                            ? "还没有播放记录"
                            : (library.selectedId === "__favorites__"
                                ? "还没有喜欢的歌曲"
                                : "这个歌单还是空的"))
                    emptyDescription: library.selectedIsRemote
                        ? "部分歌单需要会员权限才能读取完整曲目"
                        : "在搜索页或发现页右键歌曲即可添加"
                    onTrackActivated: function (index) {
                        player.playTrackInList(library.tracksModel.allItems(), index)
                    }
                    onRequestPlayNow: player.playTrack(track)
                    onRequestPlayNext: player.playNextTrack(track)
                    onRequestAppend: player.appendToQueue(track)
                    onRequestFavorite: library.toggleFavorite(track)
                }
            }
        }
    }

    // ══ 歌单右键菜单 ════════════════════════════════════
    FluMenu {
        id: plMenu
        property string targetId: ""
        property string targetName: ""
        property bool targetSystem: false
        width: 180

        FluMenuItem {
            text: "播放"
            onClicked: {
                library.select(plMenu.targetId)
                player.playTrackInList(library.tracksModel.allItems(), 0)
            }
        }
        FluMenuItem {
            text: "重命名"
            enabled: !plMenu.targetSystem
            onClicked: {
                renameDialog.targetId = plMenu.targetId
                renameDialog.openWith(plMenu.targetName)
            }
        }
        FluMenuItem {
            text: "清空歌单"
            enabled: !plMenu.targetSystem
            onClicked: library.clearPlaylist(plMenu.targetId)
        }
        FluMenuSeparator { visible: !plMenu.targetSystem }
        FluMenuItem {
            text: "删除歌单"
            visible: !plMenu.targetSystem
            onClicked: {
                deleteDialog.targetId = plMenu.targetId
                deleteDialog.targetName = plMenu.targetName
                deleteDialog.open()
            }
        }
        FluMenuItem {
            text: "清空播放历史"
            visible: plMenu.targetId === "__history__"
            onClicked: library.clearHistory()
        }
    }

    // ══ 新建 / 重命名 ═══════════════════════════════════
    InputDialog {
        id: createDialog
        title: "新建歌单"
        placeholder: "歌单名称"
        onAccepted: function (value) {
            if (value === "")
                return
            library.createPlaylist(value)
        }
    }

    InputDialog {
        id: renameDialog
        property string targetId: ""
        title: "重命名歌单"
        placeholder: "歌单名称"
        onAccepted: function (value) {
            if (value === "")
                return
            library.renamePlaylist(targetId, value)
        }
    }

    // ══ 删除确认 ════════════════════════════════════════
    FluContentDialog {
        id: deleteDialog
        property string targetId: ""
        property string targetName: ""
        title: "删除歌单"
        message: "确定要删除歌单「" + targetName + "」吗？此操作不可撤销。"
        positiveText: "删除"
        negativeText: "取消"
        buttonFlags: FluContentDialogType.NegativeButton | FluContentDialogType.PositiveButton
        onPositiveClicked: {
            library.deletePlaylist(targetId)
            close()
        }
    }
}
