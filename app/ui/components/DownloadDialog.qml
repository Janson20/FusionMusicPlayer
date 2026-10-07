import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import FluentUI
import ".."

/*!
    批量下载对话框（多选 → 「下载…」）。

    一次性定下：音质、目标目录、要附带写什么（歌词 / 标签 / 内嵌封面 / 完成后入库）、
    同名怎么处理。每一档音质都实时显示**这批曲目的预计体积** —— 无损一首几十 MB，
    不先看清楚很容易把盘写满。

    默认值全部来自「设置 → 下载」（``download.defaults()``），对话框里改的这次生效，
    不会悄悄改设置（想固定下来就到设置页改）。
*/
FluContentDialog {
    id: control
    objectName: "downloadDialog"

    property var tracks: []
    property string quality: "320k"
    property string directory: ""
    property bool writeTags: true
    property bool embedCover: true
    property bool saveLyric: true
    property bool addToLibrary: false
    property string duplicate: "rename"

    readonly property var qualityChoices: download.estimateOptions(control.tracks)
    //: 当前档位下的汇总（``{count, sizeText}``）—— 注意是对象，不能声明成 string
    readonly property var summary: {
        var list = control.qualityChoices
        for (var i = 0; i < list.length; i++) {
            if (list[i].id === control.quality)
                return list[i]
        }
        return { count: control.tracks ? control.tracks.length : 0, sizeText: "" }
    }

    title: "下载 " + (control.tracks ? control.tracks.length : 0) + " 首歌曲"
    positiveText: "开始下载"
    negativeText: "取消"
    buttonFlags: FluContentDialogType.NegativeButton | FluContentDialogType.PositiveButton
    onPositiveClicked: control.startDownload()

    /*! 按设置里的默认值把对话框准备好（不弹出来）。拆出来是为了能被测试驱动。 */
    function prepare(trackList) {
        if (!trackList || trackList.length === 0)
            return false
        control.tracks = trackList
        var defaults = download.defaults()
        control.quality = String(defaults.quality)
        control.directory = String(defaults.directory)
        control.writeTags = defaults.writeTags
        control.embedCover = defaults.embedCover
        control.saveLyric = defaults.saveLyric
        control.addToLibrary = defaults.addToLibrary
        control.duplicate = String(defaults.duplicate)
        return true
    }

    function openFor(trackList) {
        if (prepare(trackList))
            open()
    }

    function startDownload() {
        var count = download.enqueueBatch(control.tracks, {
            "quality": control.quality,
            "directory": control.directory,
            "writeTags": control.writeTags,
            "embedCover": control.embedCover,
            "saveLyric": control.saveLyric,
            "addToLibrary": control.addToLibrary,
            "duplicate": control.duplicate
        })
        return count
    }

    contentDelegate: Component {
        Item {
            implicitHeight: form.implicitHeight + 8

            ColumnLayout {
                id: form
                width: parent.width
                spacing: 10

                // ── 音质 ────────────────────────────────
                FluText {
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    text: "音质"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    spacing: 2

                    Repeater {
                        model: control.qualityChoices
                        delegate: FluRadioButton {
                            required property var modelData
                            text: modelData.name + (modelData.sizeText !== ""
                                  ? "（约 " + modelData.sizeText + "）" : "")
                            checked: control.quality === modelData.id
                            clickListener: function () { control.quality = modelData.id }
                        }
                    }
                }

                FluText {
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Layout.fillWidth: true
                    text: "该音源没有所选档位时会自动降到下一档，下载结果里会注明实际音质；"
                          + "会员曲目只能拿到试听片段时会被判为失败，不写成完整歌曲。"
                    font.pixelSize: 11
                    color: Theme.textTertiary
                    wrapMode: Text.WordWrap
                }

                // ── 目录 ────────────────────────────────
                FluText {
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Layout.topMargin: 4
                    text: "保存到"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }

                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    spacing: 8

                    FluText {
                        objectName: "downloadDialogDirectory"
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        text: control.directory
                        font.pixelSize: 12
                        color: Theme.textSecondary
                        elide: Text.ElideMiddle
                    }
                    FluButton {
                        text: "选择…"
                        onClicked: folderDialog.open()
                    }
                    FluButton {
                        text: "打开"
                        onClicked: download.openPath(control.directory)
                    }
                }

                // ── 附带内容 ────────────────────────────
                FluText {
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Layout.topMargin: 4
                    text: "下载内容"
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    spacing: 4

                    FluCheckBox {
                        objectName: "downloadDialogLyric"
                        text: "保存歌词（同名 .lrc，UTF-8）"
                        checked: control.saveLyric
                        clickListener: function () { control.saveLyric = !control.saveLyric }
                    }
                    FluCheckBox {
                        objectName: "downloadDialogTags"
                        text: "写入标题 / 歌手 / 专辑标签"
                        checked: control.writeTags
                        clickListener: function () { control.writeTags = !control.writeTags }
                    }
                    FluCheckBox {
                        objectName: "downloadDialogCover"
                        text: "内嵌封面（需要先勾上写标签）"
                        checked: control.embedCover
                        enabled: control.writeTags
                        clickListener: function () { control.embedCover = !control.embedCover }
                    }
                    FluCheckBox {
                        objectName: "downloadDialogLibrary"
                        text: "下载完成后加入「本地音乐」"
                        checked: control.addToLibrary
                        clickListener: function () { control.addToLibrary = !control.addToLibrary }
                    }
                }

                FluText {
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Layout.fillWidth: true
                    visible: !download.tagsAvailable
                    text: "未安装 mutagen：标签与内嵌封面不会写入（音频与歌词照常下载）"
                    font.pixelSize: 11
                    color: Theme.warning
                    wrapMode: Text.WordWrap
                }

                // ── 同名处理 ────────────────────────────
                RowLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Layout.topMargin: 4
                    spacing: 10

                    FluText {
                        Layout.alignment: Qt.AlignVCenter
                        text: "同名文件"
                        font.pixelSize: 13
                        color: Theme.textPrimary
                    }

                    FluComboBox {
                        objectName: "downloadDialogDuplicate"
                        Layout.preferredWidth: 220
                        model: {
                            var names = []
                            var options = download.duplicateOptions
                            for (var i = 0; i < options.length; i++)
                                names.push(options[i].name)
                            return names
                        }
                        currentIndex: {
                            var options = download.duplicateOptions
                            for (var i = 0; i < options.length; i++)
                                if (options[i].id === control.duplicate) return i
                            return 0
                        }
                        onActivated: function (index) {
                            control.duplicate = download.duplicateOptions[index].id
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                // ── 汇总 ────────────────────────────────
                FluText {
                    objectName: "downloadDialogSummary"
                    Layout.leftMargin: 20
                    Layout.rightMargin: 20
                    Layout.topMargin: 2
                    Layout.bottomMargin: 4
                    Layout.fillWidth: true
                    text: "共 " + control.summary.count + " 首"
                          + (control.summary.sizeText !== "" ? "，预计 " + control.summary.sizeText : "")
                    font.pixelSize: 12
                    color: Theme.accent
                    wrapMode: Text.WordWrap
                }
            }
        }
    }

    FolderDialog {
        id: folderDialog
        objectName: "downloadFolderDialog"
        title: "选择下载目录"
        acceptLabel: "选择"
        rejectLabel: "取消"
        onAccepted: control.directory = download.normalizeDir(selectedFolder.toString())
    }
}
