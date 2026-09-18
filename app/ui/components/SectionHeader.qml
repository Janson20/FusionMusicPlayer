import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    区块标题：标题 + 可选副标题 + 可选右侧操作。
*/
Item {
    id: control

    property string title: ""
    property string subtitle: ""
    property string actionText: ""
    property int iconSource: 0

    signal actionTriggered

    implicitHeight: 34

    RowLayout {
        anchors.fill: parent
        spacing: 10

        Rectangle {
            visible: control.iconSource !== 0
            Layout.preferredWidth: 4
            Layout.preferredHeight: 16
            Layout.alignment: Qt.AlignVCenter
            radius: 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.accent }
                GradientStop { position: 1.0; color: Theme.accentGradientEnd }
            }
        }

        FluText {
            text: control.title
            font.pixelSize: 15
            font.weight: Font.DemiBold
            color: Theme.textPrimary
            Layout.alignment: Qt.AlignVCenter
        }

        FluText {
            visible: control.subtitle !== ""
            text: control.subtitle
            font.pixelSize: 11
            color: Theme.textTertiary
            Layout.alignment: Qt.AlignVCenter
        }

        Item { Layout.fillWidth: true }

        FluTextButton {
            visible: control.actionText !== ""
            text: control.actionText
            Layout.alignment: Qt.AlignVCenter
            onClicked: control.actionTriggered()
        }
    }
}
