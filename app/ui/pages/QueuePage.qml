import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    播放队列页：查看 / 跳转 / 调整顺序 / 删除。
*/
Item {
    id: control

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 14

        SectionHeader {
            Layout.fillWidth: true
            title: "当前播放队列"
            subtitle: player.queueCount + " 首 · " + player.modeLabel
            actionText: player.queueCount > 0 ? "清空队列" : ""
            onActionTriggered: clearDialog.open()
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border
            clip: true

            ListView {
                id: queueList
                anchors.fill: parent
                anchors.margins: 6
                clip: true
                spacing: 2
                model: player.queueItems
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: FluScrollBar { }

                delegate: Rectangle {
                    id: qRow
                    required property var modelData
                    required property int index

                    width: queueList.width
                    height: 52
                    radius: Theme.radiusSmall
                    color: player.queueIndex === index
                        ? Theme.accentSoft
                        : (qMouse.containsMouse ? Theme.cardHover : "transparent")
                    Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 6
                        spacing: 12

                        FluText {
                            Layout.preferredWidth: 26
                            Layout.alignment: Qt.AlignVCenter
                            horizontalAlignment: Text.AlignRight
                            text: (index + 1)
                            font.pixelSize: 12
                            color: player.queueIndex === index ? Theme.accent : Theme.textTertiary
                        }

                        CoverArt {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            Layout.alignment: Qt.AlignVCenter
                            radiusSize: Theme.radiusSmall
                            source: modelData.cover
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3

                            FluText {
                                Layout.fillWidth: true
                                text: modelData.name
                                font.pixelSize: 13
                                font.weight: player.queueIndex === index ? Font.DemiBold : Font.Normal
                                color: player.queueIndex === index ? Theme.accent : Theme.textPrimary
                                elide: Text.ElideRight
                            }
                            FluText {
                                Layout.fillWidth: true
                                text: modelData.singer !== ""
                                    ? modelData.singer + "  ·  " + modelData.album
                                    : modelData.album
                                font.pixelSize: 11
                                color: Theme.textTertiary
                                elide: Text.ElideRight
                            }
                        }

                        FluText {
                            Layout.alignment: Qt.AlignVCenter
                            text: modelData.sourceText
                            font.pixelSize: 10
                            color: Theme.textTertiary
                        }

                        FluText {
                            Layout.preferredWidth: 46
                            Layout.alignment: Qt.AlignVCenter
                            horizontalAlignment: Text.AlignRight
                            text: modelData.durationText
                            font.pixelSize: 11
                            color: Theme.textTertiary
                        }

                        FluIconButton {
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.ChevronUp
                            iconColor: Theme.textSecondary
                            text: "上移"
                            opacity: qMouse.containsMouse ? 1 : 0
                            enabled: index > 0
                            onClicked: player.moveQueueItem(index, index - 1)
                        }

                        FluIconButton {
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.ChevronDown
                            iconColor: Theme.textSecondary
                            text: "下移"
                            opacity: qMouse.containsMouse ? 1 : 0
                            enabled: index < queueList.count - 1
                            onClicked: player.moveQueueItem(index, index + 1)
                        }

                        FluIconButton {
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.Delete
                            iconColor: Theme.textSecondary
                            text: "从队列移除"
                            opacity: qMouse.containsMouse ? 1 : 0
                            onClicked: player.removeQueueIndex(index)
                        }
                    }

                    MouseArea {
                        id: qMouse
                        anchors.fill: parent
                        anchors.rightMargin: 100
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onDoubleClicked: player.playQueueAt(index)
                    }
                }

                EmptyState {
                    anchors.fill: parent
                    visible: queueList.count === 0
                    iconSource: FluentIcons.List
                    title: "播放队列是空的"
                    description: "在搜索页双击歌曲，或右键选择「添加到播放队列」"
                }
            }
        }
    }

    FluContentDialog {
        id: clearDialog
        title: "清空播放队列"
        message: "确定要清空当前播放队列吗？"
        positiveText: "清空"
        negativeText: "取消"
        buttonFlags: FluContentDialogType.NegativeButton | FluContentDialogType.PositiveButton
        onPositiveClicked: {
            player.clearQueue()
            close()
        }
    }
}
