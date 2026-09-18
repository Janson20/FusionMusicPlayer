import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    歌单卡片：封面 + 名称 + 播放量，悬停时浮起并显示播放按钮。
*/
Item {
    id: control

    property string title: ""
    property string subtitle: ""
    property string cover: ""
    property int trackCount: 0
    property bool remote: false

    signal activated
    signal playRequested

    implicitHeight: width + 54

    Rectangle {
        id: card
        anchors.fill: parent
        radius: Theme.radiusLarge
        color: cardMouse.containsMouse ? Theme.cardHover : Theme.cardBg
        border.width: 1
        border.color: cardMouse.containsMouse ? Theme.accentSoft : Theme.border

        Behavior on color { ColorAnimation { duration: Theme.durationFast } }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 8

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: width
                Layout.maximumHeight: control.width - 20

                CoverArt {
                    id: art
                    anchors.fill: parent
                    source: control.cover
                    radiusSize: Theme.radius
                }

                // 播放量遮罩
                Rectangle {
                    visible: control.subtitle !== ""
                    anchors {
                        right: parent.right
                        top: parent.top
                        margins: 6
                    }
                    width: playRow.implicitWidth + 14
                    height: 20
                    radius: 10
                    color: Qt.rgba(0, 0, 0, 0.5)

                    Row {
                        id: playRow
                        anchors.centerIn: parent
                        spacing: 4
                        FluIcon {
                            iconSource: FluentIcons.Play
                            iconSize: 9
                            iconColor: "#FFFFFF"
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        FluText {
                            text: control.subtitle
                            font.pixelSize: 10
                            color: "#FFFFFF"
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }

                // 悬停播放按钮
                Rectangle {
                    id: playButton
                    anchors {
                        right: parent.right
                        bottom: parent.bottom
                        margins: 10
                    }
                    width: 38
                    height: 38
                    radius: 19
                    color: Theme.accent
                    opacity: cardMouse.containsMouse ? 1 : 0
                    scale: cardMouse.containsMouse ? 1 : 0.7

                    Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
                    Behavior on scale {
                        NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutBack }
                    }

                    FluIcon {
                        anchors.centerIn: parent
                        iconSource: FluentIcons.PlaySolid
                        iconSize: 15
                        iconColor: Theme.accentText
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: function (mouse) {
                            mouse.accepted = true
                            control.playRequested()
                        }
                    }
                }
            }

            FluText {
                Layout.fillWidth: true
                text: control.title
                font.pixelSize: 12
                font.weight: Font.DemiBold
                color: Theme.textPrimary
                elide: Text.ElideRight
                maximumLineCount: 2
                wrapMode: Text.WordWrap
            }
        }

        MouseArea {
            id: cardMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: control.activated()
        }
    }
}
