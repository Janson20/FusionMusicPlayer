import QtQuick
import ".."

/*!
    歌曲「另存为」对话框（右键 → 下载 → 某一档音质）。

    与封面保存同一套骨架（见 SaveFileDialog.qml）：默认文件名与目录来自
    download.saveAsHint()，用户确认后交给 download.saveAs()；
    下载、写标签、写歌词都在 Python 的工作线程里做，界面不阻塞。

    扩展名只是**猜**的：真正落盘时 Python 会按文件头纠正（B 站回的是 m4a、
    无损档拿到的可能是 flac 而不是地址写着的 mp3），并在通知里说明。
*/
SaveFileDialog {
    id: control

    objectName: "downloadSaveDialog"
    title: "下载歌曲"
    acceptLabel: "下载"
    defaultSuffix: "mp3"
    nameFilters: ["音频文件 (*.mp3 *.flac *.m4a *.ogg *.wav *.aac *.ape *.wma)", "所有文件 (*)"]

    hintProvider: function (track, quality) {
        return download.saveAsHint(track, String(quality || ""))
    }

    acceptHandler: function (track, quality, url) {
        download.saveAs(track, String(quality || ""), url)
    }
}
