import QtQuick
import QtQuick.Effects
import ".."

/*!
    背景层本体：主题底色 + 可选的自定义背景图（不透明度 / 磨砂 / 蒙版）。

    两处在用：

    * 窗口背景（``AppBackground.qml``，接在 ``FluWindow.background`` 上）；
    * **覆盖层页面**（歌词页、歌单 / 专辑 / 歌手详情）—— 它们铺满内容区，
      需要自己画一遍背景，而不是"半透明地压在底下的页面上"：那样会透过上一页的
      卡片与列表，看着像两层内容叠在一起。自绘一份就把底下挡住了，同时还能看到图。

    性能
    ----
    * 解码尺寸按 ``sourceSize`` 限到长边 2560：4K 原图整张进内存/显存没必要，
      窗口再大也就这么大；
    * 图层开了 ``layer.enabled``：背景是静态的，不该因为播放进度条在动就每帧
      重算一遍全窗口模糊。
*/
Item {
    id: control

    readonly property bool active: settings.backgroundActive

    // 长边解码上限（这里指图片像素，与窗口逻辑尺寸无关）
    readonly property int decodeLimit: 2560
    readonly property int srcWidth: settings.backgroundImageWidth
    readonly property int srcHeight: settings.backgroundImageHeight
    readonly property bool sized: srcWidth > 0 && srcHeight > 0
    readonly property real decodeScale: sized
        ? Math.min(1.0, decodeLimit / Math.max(srcWidth, srcHeight)) : 1.0

    // 底色永远先铺一层：图还没解码好、或者用户把不透明度拉到 0 时，
    // 界面依然是主题底色，而不是一块黑或透明
    Rectangle {
        objectName: "backgroundBase"
        anchors.fill: parent
        color: Theme.windowBg
    }

    Item {
        id: photoLayer
        anchors.fill: parent
        visible: control.active
        layer.enabled: control.active
        layer.smooth: true

        Image {
            id: photo
            objectName: "appBackgroundImage"
            anchors.fill: parent
            visible: false                      // 由 MultiEffect 负责绘制
            source: control.active ? settings.backgroundImage : ""
            fillMode: Image.PreserveAspectCrop    // 铺满、按比例裁切，不拉伸变形
            asynchronous: true                    // 大图解码别卡住界面
            cache: true
            smooth: true
            // 模糊会把边缘采样到图外，稍微放大一点避免四周出现一圈透明
            scale: 1.0 + settings.backgroundBlur / 100 * 0.08
            sourceSize.width: control.sized
                ? Math.max(1, Math.round(control.srcWidth * control.decodeScale)) : 0
            sourceSize.height: control.sized
                ? Math.max(1, Math.round(control.srcHeight * control.decodeScale)) : 0
        }

        MultiEffect {
            objectName: "appBackgroundEffect"
            anchors.fill: parent
            source: photo
            opacity: settings.backgroundOpacity / 100
            blurEnabled: settings.backgroundBlur > 0
            blur: settings.backgroundBlur / 100
            blurMax: 64
        }
    }

    // 蒙版：暗色主题压黑、浅色主题提白，保证上面的文字与卡片读得清
    Rectangle {
        objectName: "windowBackgroundScrim"
        anchors.fill: parent
        visible: control.active
        color: Theme.dark ? "#000000" : "#FFFFFF"
        opacity: settings.backgroundScrim / 100
    }
}
