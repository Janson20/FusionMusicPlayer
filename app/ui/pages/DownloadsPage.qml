import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    下载页：任务列表、进度、失败原因与重试。

    进度靠 ``download.setPolling(visible)``：只有这一页可见时才每 300ms 搬一次快照
    （不可见时白刷没意义）。列表模型按 id 做增量更新，所以进度条不会每次从头动画。
*/
Item {
    id: control
    objectName: "downloadsPage"

    // ── 顶部：标题 + 计数 + 批量操作 ────────────────────
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            FluText {
                Layout.alignment: Qt.AlignVCenter
                text: "下载"
                font.pixelSize: 20
                font.weight: Font.Bold
                color: Theme.textPrimary
            }

            FluText {
                objectName: "downloadsSummaryText"
                Layout.alignment: Qt.AlignVCenter
                text: control.summaryText()
                font.pixelSize: 12
                color: Theme.textTertiary
            }

            Item { Layout.fillWidth: true }

            FluProgressRing {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                Layout.alignment: Qt.AlignVCenter
                strokeWidth: 3
                visible: download.activeCount > 0
            }

            FluButton {
                objectName: "downloadsCancelAllButton"
                text: "全部取消"
                disabled: download.activeCount === 0
                onClicked: download.cancelAll()
            }
            FluButton {
                objectName: "downloadsRetryFailedButton"
                text: "重试失败"
                disabled: download.counts.failed === 0
                onClicked: {
                    var count = download.retryFailed()
                    if (count === 0)
                        app.warn("没有可重试的任务")
                }
            }
            FluButton {
                objectName: "downloadsClearFinishedButton"
                text: "清空已完成"
                disabled: download.finishedCount === 0
                onClicked: download.clearFinished()
            }
            FluButton {
                objectName: "downloadsOpenFolderButton"
                text: "打开下载目录"
                onClicked: download.openPath(download.downloadDir)
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border
            clip: true

            ListView {
                id: taskList
                anchors.fill: parent
                anchors.margins: 6
                visible: download.tasks.count > 0
                model: download.tasks
                spacing: 2
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                reuseItems: true
                ScrollBar.vertical: FluScrollBar { }

                delegate: Rectangle {
                    id: row
                    required property int index
                    required property int id
                    required property string name
                    required property string singer
                    required property string sourceText
                    required property string cover
                    required property string qualityLabel
                    required property string qualityActualLabel
                    required property bool degraded
                    required property string state
                    required property string stateText
                    required property bool active
                    required property bool finished
                    required property real progress
                    required property string sizeText
                    required property string speedText
                    required property string error
                    required property string warning
                    required property string path
                    required property string fileName
                    required property string directory

                    objectName: "downloadTaskRow"
                    width: taskList.width
                    height: 62
                    radius: Theme.radiusSmall
                    color: rowMouse.containsMouse ? Theme.cardHover : "transparent"

                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        acceptedButtons: Qt.NoButton
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: 12

                        CoverArt {
                            Layout.preferredWidth: 36
                            Layout.preferredHeight: 36
                            Layout.alignment: Qt.AlignVCenter
                            radiusSize: Theme.radiusSmall
                            source: row.cover
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            spacing: 3

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8

                                FluText {
                                    Layout.fillWidth: true
                                    text: row.name
                                    font.pixelSize: 13
                                    color: Theme.textPrimary
                                    elide: Text.ElideRight
                                }
                                FluText {
                                    text: row.singer
                                    font.pixelSize: 11
                                    color: Theme.textTertiary
                                    elide: Text.ElideRight
                                    Layout.maximumWidth: 220
                                }
                            }

                            FluProgressBar {
                                objectName: "downloadTaskProgress"
                                Layout.fillWidth: true
                                Layout.preferredHeight: 4
                                visible: row.active && row.state === "downloading"
                                indeterminate: false
                                from: 0
                                to: 1
                                value: row.progress
                            }

                            FluText {
                                Layout.fillWidth: true
                                text: control.rowDetail(row)
                                font.pixelSize: 11
                                color: control.rowDetailColor(row)
                                elide: Text.ElideMiddle
                            }
                        }

                        FluText {
                            Layout.alignment: Qt.AlignVCenter
                            Layout.preferredWidth: 130
                            horizontalAlignment: Text.AlignRight
                            text: row.sizeText !== "" ? row.sizeText : ""
                            font.pixelSize: 11
                            color: Theme.textTertiary
                            elide: Text.ElideRight
                        }

                        FluText {
                            Layout.alignment: Qt.AlignVCenter
                            Layout.preferredWidth: 76
                            text: row.speedText
                            font.pixelSize: 11
                            color: Theme.textTertiary
                        }

                        Rectangle {
                            Layout.preferredWidth: stateText.implicitWidth + 16
                            Layout.preferredHeight: 18
                            Layout.alignment: Qt.AlignVCenter
                            radius: 9
                            color: control.stateColor(row)
                            opacity: 0.16
                            FluText {
                                id: stateText
                                anchors.centerIn: parent
                                text: row.stateText
                                font.pixelSize: 10
                                color: control.stateColor(row)
                            }
                        }

                        FluIconButton {
                            objectName: "downloadTaskCancelButton"
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.Cancel
                            iconColor: Theme.textSecondary
                            text: "取消"
                            visible: row.active
                            onClicked: download.cancel(row.id)
                        }
                        FluIconButton {
                            objectName: "downloadTaskRetryButton"
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.Refresh
                            iconColor: Theme.textSecondary
                            text: "重试"
                            visible: row.finished && row.state !== "done"
                            onClicked: download.retry(row.id)
                        }
                        FluIconButton {
                            objectName: "downloadTaskOpenButton"
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.Play
                            iconColor: Theme.textSecondary
                            text: "播放"
                            visible: row.state === "done" && row.path !== ""
                            onClicked: download.playTask(row.id)
                        }
                        FluIconButton {
                            objectName: "downloadTaskFolderButton"
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.FolderOpen
                            iconColor: Theme.textSecondary
                            text: "在文件夹中显示"
                            visible: row.state === "done" && row.path !== ""
                            onClicked: download.showInFolder(row.id)
                        }
                        FluIconButton {
                            objectName: "downloadTaskRemoveButton"
                            Layout.preferredWidth: 28
                            Layout.preferredHeight: 28
                            Layout.alignment: Qt.AlignVCenter
                            iconSize: 13
                            iconSource: FluentIcons.Delete
                            iconColor: Theme.textSecondary
                            text: "从列表移除"
                            visible: row.finished
                            onClicked: download.removeTask(row.id)
                        }
                    }

                    FluTooltip {
                        visible: rowMouse.containsMouse && row.path !== ""
                        text: row.path
                        delay: 600
                    }
                }
            }

            EmptyState {
                anchors.fill: parent
                visible: download.tasks.count === 0
                iconSource: FluentIcons.Download
                title: "还没有下载任务"
                description: "在曲目上点右键 →「下载」，或选中多首后点工具条上的「下载…」"
            }
        }
    }

    /*! 列表底部那行小字：状态、失败原因、降级说明都挤在这里。 */
    function rowDetail(task) {
        if (task.state === "failed")
            return task.error !== "" ? task.error : "下载失败"
        if (task.state === "skipped")
            return task.warning !== "" ? task.warning : "同名文件已存在"
        if (task.state === "canceled")
            return task.warning !== "" ? task.warning : "已取消"
        if (task.state === "done") {
            var text = task.fileName
            if (task.degraded)
                text += " · 实际音质 " + task.qualityActualLabel
            if (task.warning !== "")
                text += " · " + task.warning
            return text
        }
        if (task.state === "downloading")
            return task.qualityLabel + " · 正在下载"
        return task.qualityLabel
    }

    function rowDetailColor(task) {
        if (task.state === "failed")
            return Theme.danger
        if (task.state === "done" && task.degraded)
            return Theme.warning
        return Theme.textTertiary
    }

    function stateColor(task) {
        if (task.state === "failed")
            return Theme.danger
        if (task.state === "done")
            return Theme.success
        if (task.state === "skipped" || task.state === "canceled")
            return Theme.textSecondary
        return Theme.accent
    }

    function summaryText() {
        var counts = download.counts
        if (counts.total === 0)
            return "还没有任务"
        var parts = []
        if (counts.active > 0)
            parts.push("进行中 " + counts.active)
        if (counts.done > 0)
            parts.push("成功 " + counts.done)
        if (counts.failed > 0)
            parts.push("失败 " + counts.failed)
        if (counts.skipped > 0)
            parts.push("跳过 " + counts.skipped)
        if (counts.canceled > 0)
            parts.push("取消 " + counts.canceled)
        return parts.join(" · ")
    }

    onVisibleChanged: download.setPolling(visible)
}
