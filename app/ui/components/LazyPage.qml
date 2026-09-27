import QtQuick

/*!
    惰性页面容器（Main.qml 的 StackLayout 用）。

    6 个页面若在启动时全部编译 + 实例化，实测占 engine.load 约 0.3 秒，
    而首帧只会显示其中一个 —— 其余 5 个纯属白等。这里改成"第一次成为
    当前页时才加载"：

    * ``current``    由 Main.qml 按 ``StackLayout.currentIndex`` 绑定过来；
    * ``everLoaded`` 加载过就一直留着，切走**不销毁** —— 页面里的搜索词、
      滚动位置、展开状态都得原样保留，销毁重建等于把用户的操作抹掉。

    ``source`` 用相对路径写在 Main.qml 里：QML 的相对 URL 按**写它的那个文件**
    解析，所以这里写 ``"pages/DiscoverPage.qml"`` 指的是 Main.qml 旁边那个目录。
*/
Loader {
    id: control

    property bool current: false
    property bool everLoaded: false

    // 同步加载：切页时要立刻看到内容，异步反而先闪一下空白
    asynchronous: false
    active: current || everLoaded

    // 注意：这里只能监听 current 的变化，**不能**监听 active ——
    // active 绑定依赖 everLoaded，而 active 变化又去写 everLoaded，
    // Qt 会判定成绑定循环并丢掉 active 的绑定（实测报
    // "Binding loop detected for property active"）。
    onCurrentChanged: {
        if (current)
            control.everLoaded = true
    }

    // 初始就是当前页时 onCurrentChanged 不会触发，这里补一次
    Component.onCompleted: {
        if (control.current)
            control.everLoaded = true
    }
}
