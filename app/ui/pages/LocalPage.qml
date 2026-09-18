import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    本地音乐：管理扫描文件夹 + 展示本地曲库。
*/
Item {
    id: control

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 14

        // ── 文件夹管理 ──────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: folderColumn.height + 24
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border

            ColumnLayout {
                id: folderColumn
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    margins: 12
                }
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    FluText {
                        text: "扫描文件夹"
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                        Layout.alignment: Qt.AlignVCenter
                    }

                    FluText {
                        text: library.localModel.count + " 首本地歌曲"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        Layout.alignment: Qt.AlignVCenter
                    }

                    Item { Layout.fillWidth: true }

                    FluProgressRing {
                        Layout.preferredWidth: 20
                        Layout.preferredHeight: 20
                        Layout.alignment: Qt.AlignVCenter
                        strokeWidth: 3
                        visible: library.scanning
                    }

                    FluText {
                        Layout.alignment: Qt.AlignVCenter
                        visible: library.scanning
                        text: "扫描中 " + library.scanProgress + "%"
                        font.pixelSize: 11
                        color: Theme.accent
                    }

                    FluButton {
                        text: "添加文件夹"
                        onClicked: folderDialog.openWith("")
                    }

                    FluFilledButton {
                        text: "重新扫描"
                        disabled: library.scanning || library.localFolders.length === 0
                        onClicked: library.scan()
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? implicitHeight : 0
                    visible: library.localFolders.length > 0
                    spacing: 8

                    Repeater {
                        model: library.localFolders
                        delegate: Rectangle {
                            required property string modelData
                            width: Math.min(360, folderText.implicitWidth + 48)
                            height: 30
                            radius: 15
                            color: Theme.dark ? "#252431" : "#F0EFF7"

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 6
                                spacing: 6

                                FluIcon {
                                    Layout.alignment: Qt.AlignVCenter
                                    iconSource: FluentIcons.Folder
                                    iconSize: 12
                                    iconColor: Theme.textSecondary
                                }
                                FluText {
                                    id: folderText
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                    text: modelData
                                    font.pixelSize: 11
                                    color: Theme.textSecondary
                                    elide: Text.ElideMiddle
                                }
                                FluIconButton {
                                    Layout.preferredWidth: 22
                                    Layout.preferredHeight: 22
                                    Layout.alignment: Qt.AlignVCenter
                                    iconSize: 11
                                    iconSource: FluentIcons.Cancel
                                    iconColor: Theme.textTertiary
                                    text: "移除"
                                    onClicked: library.removeLocalFolder(modelData)
                                }
                            }
                        }
                    }
                }

                FluText {
                    Layout.fillWidth: true
                    visible: library.localFolders.length === 0
                    text: "还没有添加文件夹。点击「添加文件夹」把本地音乐目录加进来，程序会读取标签与时长。"
                    font.pixelSize: 11
                    color: Theme.textTertiary
                    wrapMode: Text.WordWrap
                }
            }
        }

        // ── 曲目列表 ────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border
            clip: true

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 6
                spacing: 0

                SectionHeader {
                    Layout.fillWidth: true
                    Layout.leftMargin: 8
                    Layout.rightMargin: 8
                    Layout.bottomMargin: 4
                    title: "全部本地歌曲"
                    subtitle: library.localModel.count + " 首"
                    actionText: library.localModel.count > 0 ? "播放全部" : ""
                    onActionTriggered: player.playTrackInList(library.localModel.allItems(), 0)
                }

                TrackListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: library.localModel
                    showSource: false
                    busy: library.scanning
                    emptyIcon: FluentIcons.Folder
                    emptyTitle: "本地曲库为空"
                    emptyDescription: "添加一个音乐文件夹后点击「重新扫描」"
                    emptyActionText: "添加文件夹"
                    onEmptyActionTriggered: folderDialog.openWith("")
                    onTrackActivated: function (index) {
                        player.playTrackInList(library.localModel.allItems(), index)
                    }
                    onRequestPlayNow: function (track) { player.playTrack(track) }
                    onRequestPlayNext: function (track) { player.playNextTrack(track) }
                    onRequestAppend: function (track) { player.appendToQueue(track) }
                    onRequestFavorite: function (track) { library.toggleFavorite(track) }
                }
            }
        }
    }

    InputDialog {
        id: folderDialog
        title: "添加音乐文件夹"
        label: "粘贴文件夹的完整路径"
        placeholder: "例如 D:\\Music"
        hint: "程序会递归扫描该目录下的 mp3 / flac / m4a / wav / ogg 等音频文件。"
        onAccepted: function (value) {
            if (value === "")
                return
            library.addLocalFolder(value)
        }
    }
}
