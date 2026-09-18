import QtQuick
import QtQuick.Controls
import FluentUI
import ".."

/*!
    圆角封面，带渐变占位图与淡入效果。
*/
Rectangle {
    id: control

    property string source: ""
    property int radiusSize: Theme.radius
    property bool circle: false
    property bool showShadow: false

    radius: circle ? width / 2 : radiusSize
    color: Theme.dark ? "#2A2833" : "#E9E8F2"
    clip: true

    // 占位渐变（无封面时可见）
    Rectangle {
        anchors.fill: parent
        visible: !artwork.visible
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.dark ? "#332F45" : "#E4E0F5" }
            GradientStop { position: 1.0; color: Theme.dark ? "#23212E" : "#F2F1F9" }
        }
        FluIcon {
            anchors.centerIn: parent
            iconSource: FluentIcons.MusicNote
            iconSize: Math.max(14, Math.min(parent.width, parent.height) * 0.34)
            iconColor: Theme.dark ? "#4A4757" : "#C3BFD9"
        }
    }

    Image {
        id: artwork
        anchors.fill: parent
        source: control.source
        visible: status === Image.Ready && control.source !== ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: true
        sourceSize.width: 320
        sourceSize.height: 320
        opacity: 0

        Behavior on opacity { NumberAnimation { duration: Theme.durationNormal } }

        onStatusChanged: {
            if (status === Image.Ready)
                opacity = 1
            else
                opacity = 0
        }
    }
}
