import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    空状态 / 加载状态占位。
*/
ColumnLayout {
    id: control

    property int iconSource: FluentIcons.MusicNote
    property string title: "暂无内容"
    property string description: ""
    property string actionText: ""
    property bool busy: false

    signal actionTriggered

    spacing: 12

    Item {
        Layout.fillWidth: true
        Layout.preferredHeight: 8
    }

    FluProgressRing {
        Layout.alignment: Qt.AlignHCenter
        visible: control.busy
        width: 30
        height: 30
    }

    FluIcon {
        Layout.alignment: Qt.AlignHCenter
        visible: !control.busy
        iconSource: control.iconSource
        iconSize: 46
        iconColor: Theme.dark ? "#3A3846" : "#CFCCE0"
    }

    FluText {
        Layout.alignment: Qt.AlignHCenter
        Layout.maximumWidth: 380
        text: control.title
        font.pixelSize: 14
        font.weight: Font.DemiBold
        color: Theme.textSecondary
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
    }

    FluText {
        Layout.alignment: Qt.AlignHCenter
        Layout.maximumWidth: 420
        visible: control.description !== ""
        text: control.description
        font.pixelSize: 12
        color: Theme.textTertiary
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        lineHeight: 1.35
    }

    FluButton {
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: 4
        visible: control.actionText !== ""
        text: control.actionText
        onClicked: control.actionTriggered()
    }

    Item {
        Layout.fillWidth: true
        Layout.fillHeight: true
    }
}
