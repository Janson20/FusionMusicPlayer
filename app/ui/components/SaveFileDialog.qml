import QtQuick
import QtQuick.Dialogs

/*!
    「另存为」对话框的骨架。

    封面保存与歌曲下载两个对话框原先结构逐字相同（prepare / openFor / onAccepted
    三段），只有默认值来源与确认后的动作不同：子类给 hintProvider 与
    acceptHandler，其余（目录先于文件名、扩展名跟着走、确认后回传 URL）
    都在这里。

    extra 是附加参数：歌曲下载用它带音质档位，封面保存用不到。
*/
FileDialog {
    id: control

    fileMode: FileDialog.SaveFile
    acceptLabel: "保存"
    rejectLabel: "取消"

    //: 当前要处理的曲目（QML 里的曲目字典）
    property var trackData: null
    //: 附加参数（可空）：openFor() 传进来、prepare() 取用（歌曲下载带音质档位）
    property var pendingExtra: undefined

    //: 向 Python 要默认值：返回 {name, suffix, file, folder}
    property var hintProvider: function (track, extra) { return {} }
    //: 用户确认后回传（曲目、附加参数、file:// URL）
    property var acceptHandler: function (track, extra, url) {}

    /*! 按曲目准备好默认值，但不弹窗（冒烟测试直接调它）。

        只收**一个**参数：冒烟测试用 QMetaObject.invokeMethod 按签名找方法，
        两个参数会匹配不上（实测返回 false 且不执行）。附加参数走 pendingExtra。
    */
    function prepare(track) {
        if (!track)
            return false
        control.trackData = track
        var extra = control.pendingExtra
        var hint = control.hintProvider(track, extra)
        if (!hint)
            return false
        // 先定目录再定文件名：反过来设 currentFile 会被 currentFolder 重置掉
        currentFolder = hint.folder
        currentFile = hint.file
        defaultSuffix = String(hint.suffix)
        return true
    }

    function openFor(track, extraValue) {
        control.pendingExtra = extraValue
        if (prepare(track))
            open()
    }

    onAccepted: control.acceptHandler(control.trackData, control.pendingExtra,
                                      selectedFile.toString())
}
