import QtQuick
import QtQuick.Dialogs

/*!
    歌曲「另存为」对话框（右键 → 下载 → 某一档音质）。

    与封面保存同一套做法（见 CoverSaveDialog.qml）：默认文件名与目录来自
    ``download.saveAsHint()``，用户确认后交给 ``download.saveAs()``；
    下载、写标签、写歌词都在 Python 的工作线程里做，界面不阻塞。

    扩展名只是**猜**的：真正落盘时 Python 会按文件头纠正（B 站回的是 m4a、
    无损档拿到的可能是 flac 而不是地址写着的 mp3），并在通知里说明。
*/
FileDialog {
    id: control
    objectName: "downloadSaveDialog"

    //: 当前要下载的曲目（QML 里的曲目字典）与选定的音质档位
    property var trackData: null
    property string quality: ""

    fileMode: FileDialog.SaveFile
    title: "下载歌曲"
    acceptLabel: "下载"
    rejectLabel: "取消"
    defaultSuffix: "mp3"
    nameFilters: ["音频文件 (*.mp3 *.flac *.m4a *.ogg *.wav *.aac *.ape *.wma)", "所有文件 (*)"]

    /*! 把对话框按这首曲目准备好（默认文件名 / 目录 / 扩展名），但不弹出来。

    单独拆出来是为了能被测试驱动：``open()`` 会拉起系统原生对话框（模态、阻塞），
    冒烟测试点不了它，但「默认值准备得对不对」是我们自己的逻辑，值得单独验。
    */
    function prepare(track, qualityId) {
        if (!track)
            return false
        control.trackData = track
        control.quality = String(qualityId || "")
        var hint = download.saveAsHint(track, control.quality)
        // 先定目录再定文件名：反过来设 currentFile 会被 currentFolder 重置掉
        currentFolder = hint.folder
        currentFile = hint.file
        defaultSuffix = String(hint.suffix)
        return true
    }

    function openFor(track, qualityId) {
        if (prepare(track, qualityId))
            open()
    }

    onAccepted: download.saveAs(control.trackData, control.quality, selectedFile.toString())
}
