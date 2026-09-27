import QtQuick
import ".."

/*!
    窗口背景：背景层本体（见 ``BackgroundLayer.qml``）+ 分区不透明度的同步。

    接在 ``FluWindow.background`` 上 —— 那边是个
    ``FluLoader{anchors.fill: parent; sourceComponent: background}``，正好是留给
    我们换背景的位置。主窗口、设置窗口、登录窗口三处共用这一个组件，观感一致。
*/
Item {
    id: control

    readonly property bool active: settings.backgroundActive

    /*!
        分区不透明度是全局令牌（``Theme`` 上的四个 alpha），但只有「挂了背景层的
        窗口」需要维护它们 —— 顺手在这里同步：三个窗口都用了本组件，逻辑只写一份。
        设置窗口拖滑块时 ``settings.changed`` 会发出来，三个窗口一起跟上。

        没有背景图时一律压回 1.0（实色），界面与从前完全一致。
    */
    function syncSurfaces() {
        var on = active
        Theme.alphaSidebar = on ? settings.surfaceSidebar / 100 : 1.0
        Theme.alphaBottom = on ? settings.surfaceBottom / 100 : 1.0
        Theme.alphaOverlay = on ? settings.surfaceOverlay / 100 : 1.0
        Theme.alphaCard = on ? settings.surfaceCard / 100 : 1.0
    }

    Component.onCompleted: syncSurfaces()
    Connections {
        target: settings
        function onChanged() { control.syncSurfaces() }
    }

    BackgroundLayer {
        anchors.fill: parent
    }
}
