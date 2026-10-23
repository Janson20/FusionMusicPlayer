import QtQuick
import ".."

/*!
    封面「另存为」对话框。

    两处入口（展开播放页的大封面、播放栏左下角的小封面）共用这一个组件：
    右键 → 「保存封面…」→ openFor(track) 打开；用户选好位置后交给
    app.saveCover()。下载与落盘在 Python 的工作线程里做（可能要拉几百 KB），
    成功 / 失败都由应用通知提示，这里不阻塞界面。

    默认文件名与目录来自 app.coverSaveHint()：名字是「歌手 - 歌名」，
    目录是上次存过的那个（记在 storage.cover_dir）。扩展名只是**猜**的，
    真正落盘时 Python 会按文件头纠正（地址写 .jpg 而内容是 webp 的不少见）。

    骨架（准备默认值 / 确认后回传 URL）在 SaveFileDialog.qml，与歌曲下载共用。
*/
SaveFileDialog {
    id: control

    objectName: "coverSaveDialog"
    title: "保存封面"
    acceptLabel: "保存"
    defaultSuffix: "jpg"
    nameFilters: ["图片 (*.jpg *.jpeg *.png *.webp *.bmp *.gif)", "所有文件 (*)"]

    hintProvider: function (track) {
        return app.coverSaveHint(track)
    }

    acceptHandler: function (track, extra, url) {
        app.saveCover(track, url)
    }
}
