import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    设置项：标题 + 说明 + 开关。
*/
Item {
    id: control

    property string label: ""
    property string description: ""
    property bool checked: false
    property bool enabledControl: true

    signal toggled(bool value)

    Layout.fillWidth: true
    implicitHeight: Math.max(48, textColumn.implicitHeight + 16)

    Rectangle {
        anchors.fill: parent
        radius: Theme.radius
        color: Theme.cardBg
        border.width: 1
        border.color: Theme.border
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 12
        spacing: 12

        ColumnLayout {
            id: textColumn
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: 2

            FluText {
                Layout.fillWidth: true
                text: control.label
                font.pixelSize: 13
                color: Theme.textPrimary
                wrapMode: Text.WordWrap
            }
            FluText {
                Layout.fillWidth: true
                visible: control.description !== ""
                text: control.description
                font.pixelSize: 11
                color: Theme.textTertiary
                wrapMode: Text.WordWrap
                lineHeight: 1.25
            }
        }

        FluToggleSwitch {
            Layout.alignment: Qt.AlignVCenter
            checked: control.checked
            enabled: control.enabledControl
            text: ""
            clickListener: function () { control.toggled(!control.checked) }
        }
    }
}
