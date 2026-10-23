import QtQuick
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    设置页里的「百分比滑块」一行：标签 + 0-100 滑块 + 右侧数值。

    七个分区（背景透明度 / 磨砂 / 蒙版 + 侧边栏 / 播放栏 / 覆盖层 / 卡片）原先
    各写一段二十来行、只有 key 不同；这里把「布局 + 取整 + 百分比文案」收成一份。

    值是**单向**的（value: 绑设置、onMoved 写设置），与原先每段
    的写法一致：拖动时先改设置，设置变化再把新值送回滑块。
*/
RowLayout {
    id: control

    //: 左侧标签
    property string label: ""
    //: 当前值（0-100）
    property int value: 0
    //: 标签列宽：同一个 Grid 里几行要对齐，取该组最长标签的宽度
    property int labelWidth: 84
    //: 滑块的 objectName（冒烟测试按名字找它）
    property string sliderObjectName: ""

    //: 用户拖动后发出的新值（已取整）
    signal moved(int value)

    spacing: 12

    FluText {
        Layout.preferredWidth: control.labelWidth
        Layout.alignment: Qt.AlignVCenter
        text: control.label
        font.pixelSize: 12
        color: Theme.textSecondary
    }

    FluSlider {
        objectName: control.sliderObjectName
        Layout.preferredWidth: 240
        from: 0
        to: 100
        stepSize: 1
        value: control.value
        tooltipEnabled: true
        text: Math.round(value) + "%"
        onMoved: control.moved(Math.round(value))
    }

    FluText {
        Layout.preferredWidth: 42
        Layout.alignment: Qt.AlignVCenter
        text: control.value + "%"
        font.pixelSize: 12
        color: Theme.textTertiary
    }
}
