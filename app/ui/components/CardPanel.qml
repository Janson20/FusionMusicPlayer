import QtQuick
import ".."

/*!
    内容卡片：列表 / 面板外面那层「圆角 + 卡片底色 + 1px 边框 + 裁切」。

    九个宿主原先各写一遍这七行（页面、覆盖层、详情页都有），参数完全一样；
    分区不透明度（自定义背景图）已经折进 Theme.cardBg，所以这里不用再管。
    需要不同圆角的地方写 radius: 覆盖即可。
*/
Rectangle {
    radius: Theme.radius
    color: Theme.cardBg
    border.width: 1
    border.color: Theme.border
    clip: true
}
