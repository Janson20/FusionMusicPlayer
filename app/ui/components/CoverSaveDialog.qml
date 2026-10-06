import QtQuick
import QtQuick.Dialogs

/*!
    封面「另存为」对话框。

    两处入口（展开播放页的大封面、播放栏左下角的小封面）共用这一个组件：
    右键 → 「保存封面…」→ ``openFor(track)`` 打开；用户选好位置后交给
    ``app.saveCover()``。下载与落盘在 Python 的工作线程里做（可能要拉几百 KB），
    成功 / 失败都由应用通知提示，这里不阻塞界面。

    默认文件名与默认目录来自 ``app.coverSaveHint()``：名字是「歌手 - 歌名」，
    目录是上次存过的那个（记在 ``storage.cover_dir``）。扩展名只是**猜**的，
    真正落盘时 Python 会按文件头纠正（地址写 .jpg 而内容是 webp 的不少见）。
*/
FileDialog {
    id: control
    objectName: "coverSaveDialog"

    //: 当前要保存封面的曲目（QML 里的曲目字典）
    property var trackData: null

    fileMode: FileDialog.SaveFile
    title: "保存封面"
    acceptLabel: "保存"
    rejectLabel: "取消"
    defaultSuffix: "jpg"
    nameFilters: ["图片 (*.jpg *.jpeg *.png *.webp *.bmp *.gif)", "所有文件 (*)"]

    /*! 把对话框按这首曲目准备好（默认文件名 / 默认目录 / 扩展名），但不弹出来。

    单独拆出来是为了能被测试驱动：``open()`` 会拉起系统原生对话框（模态、阻塞），
    冒烟测试没法点它，但"默认值准备得对不对"是**我们自己的逻辑**，值得单独验。
    */
    function prepare(track) {
        if (!track)
            return false
        control.trackData = track
        var hint = app.coverSaveHint(track)
        // 先定目录再定文件名：反过来设 currentFile 会被 currentFolder 重置掉
        currentFolder = hint.folder
        currentFile = hint.file
        defaultSuffix = String(hint.suffix)
        return true
    }

    function openFor(track) {
        if (prepare(track))
            open()
    }

    onAccepted: app.saveCover(control.trackData, selectedFile.toString())
}
