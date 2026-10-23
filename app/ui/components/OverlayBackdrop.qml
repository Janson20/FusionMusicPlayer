import QtQuick
import ".."

/*!
    覆盖层的「垫底三件套」：事件遮罩 + 背景层 + 分区蒙版。

    四处在用（展开播放页、歌单 / 专辑 / 歌手详情页），原先各写二十来行，
    只有遮罩与蒙版的 objectName 不同（冒烟测试按名字找它们）。

    为什么必须有这块：面板根节点只是个普通 Item，空白处不吃鼠标事件，点击会穿到
    底下的导航栏 / 页面；而只铺半透明色的话，上一页的卡片与列表会直接透上来，
    看着像两层内容叠在一起。所以自绘一份背景层把底下挡住，同时还能看到背景图。

    用法：anchors.fill: parent + 传入两个名字，声明在其它子项之前。
*/
Item {
    id: control

    //: 事件遮罩的 objectName（冒烟测试用它验证「点不穿」）
    property string blockerObjectName: ""
    //: 蒙版的 objectName（可空）
    property string scrimObjectName: ""

    MouseArea {
        objectName: control.blockerObjectName
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onWheel: function (wheel) { wheel.accepted = true }
    }

    BackgroundLayer {
        anchors.fill: parent
    }

    Rectangle {
        objectName: control.scrimObjectName
        anchors.fill: parent
        color: Theme.windowBg
        opacity: Theme.alphaOverlay
    }
}
