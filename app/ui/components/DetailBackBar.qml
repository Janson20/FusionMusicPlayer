import QtQuick
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    覆盖层顶部那行：返回按钮 + 说明文字 + 弹性空白 + 加载转圈。

    三个详情页 + 展开播放页的「收起」按钮原先各写一遍，只有标题与名字不同。
*/
RowLayout {
    id: control

    //: 按钮右边的说明文字（"返回发现页" / "专辑" / "歌手"）
    property string title: ""
    //: 是否在右侧显示加载转圈
    property bool loading: false
    //: 返回按钮的 objectName（冒烟测试按名字找它）
    property string backObjectName: ""

    signal backRequested

    Layout.fillWidth: true
    spacing: 10

    FluIconButton {
        objectName: control.backObjectName
        Layout.preferredWidth: 34
        Layout.preferredHeight: 34
        Layout.alignment: Qt.AlignVCenter
        iconSize: 15
        iconSource: FluentIcons.ChevronLeft
        iconColor: Theme.textSecondary
        text: "返回"
        onClicked: control.backRequested()
    }

    FluText {
        Layout.alignment: Qt.AlignVCenter
        text: control.title
        font.pixelSize: 12
        color: Theme.textSecondary
    }

    Item { Layout.fillWidth: true }

    FluProgressRing {
        Layout.preferredWidth: 20
        Layout.preferredHeight: 20
        Layout.alignment: Qt.AlignVCenter
        strokeWidth: 3
        visible: control.loading
    }
}
