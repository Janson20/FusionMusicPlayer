import QtQuick
import FluentUI
import ".."

/*!
    工具窗口（设置 / 登录）的骨架。

    这两类窗口原先各写一遍同样二十来行：按屏幕夹尺寸、visible: false、
    closeDestory: false（关了只藏不销毁）、背景与主窗口一致、抵消基类的
    无条件 show()。真正要显示时调 openWindow()；需要「显示之后再
    做点什么」（登录窗口开始扫码、设置窗口刷新缓存）就接 opened 信号。

    showMaximize / fixSize 这类窗口个性由子类直接赋值。
*/
FluWindow {
    id: control

    //: 想要的尺寸与下限（会按屏幕可用区域夹一次，见 bridges/app.py 的 fit_window）
    property int wantWidth: 800
    property int wantHeight: 560
    property int wantMinWidth: 720
    property int wantMinHeight: 480

    readonly property var fitted: app.fitWindow(wantWidth, wantHeight, wantMinWidth, wantMinHeight)

    width: fitted.width
    height: fitted.height
    minimumWidth: Math.min(wantMinWidth, fitted.width)
    minimumHeight: Math.min(wantMinHeight, fitted.height)

    visible: false
    // 关闭时只隐藏、不销毁：FluWindow 默认 closeDestory=true 会 deleteLater()，
    // 之后 QML 里的 id 就成了已释放对象，再打开会报 "... of null"。
    closeDestory: false
    showStayTop: false
    showDark: false

    // 背景与主窗口一致（自定义背景图在这两个窗口里也生效）
    background: Component {
        AppBackground { }
    }

    // FluWindow 的基类 Component.onCompleted 会无条件 show()，不收回的话设置窗口
    // 会跟着主窗口一起弹出来。基类先于派生组件执行，所以这里 hide() 是可靠的。
    Component.onCompleted: hide()

    //: 窗口已经显示出来（子类在这里做「打开时该做的事」）
    signal opened

    /*! 显示窗口。子类不要覆盖它 —— 需要额外动作就接 opened。 */
    function openWindow() {
        control.visible = true
        control.requestActivate()
        control.opened()
    }
}
