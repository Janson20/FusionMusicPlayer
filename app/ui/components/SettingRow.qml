import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    设置项：只读的「标签 — 值」行，值可复制。
*/
Item {
    id: control

    property string label: ""
    property string value: ""
    property bool copyable: false

    Layout.fillWidth: true
    implicitHeight: 40

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSmall
        color: Theme.dark ? Qt.rgba(1, 1, 1, 0.03) : Qt.rgba(0, 0, 0, 0.018)
        border.width: 1
        border.color: Theme.divider
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 8
        spacing: 10

        FluText {
            Layout.preferredWidth: 92
            Layout.alignment: Qt.AlignVCenter
            text: control.label
            font.pixelSize: 12
            color: Theme.textSecondary
        }

        FluText {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            text: control.value
            font.pixelSize: 12
            color: Theme.textPrimary
            elide: Text.ElideMiddle
        }

        FluIconButton {
            Layout.preferredWidth: 26
            Layout.preferredHeight: 26
            Layout.alignment: Qt.AlignVCenter
            iconSize: 12
            iconSource: FluentIcons.Copy
            iconColor: Theme.textTertiary
            text: "复制"
            visible: control.copyable
            onClicked: settings.copyToClipboard(control.value)
        }
    }
}
