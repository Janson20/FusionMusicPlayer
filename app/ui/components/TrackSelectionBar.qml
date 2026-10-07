import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    曲目列表顶部的选择工具条（多选批量操作的入口）。

    两种形态：
    * **未进入多选**：右侧一个「多选」按钮（歌单类列表还多一个「全选」——
      用户要的就是「一键全选再批量下载」）；
    * **已进入多选**：左边「已选 N 首」，右边全选 / 批量下载 / 加入队列 / 收藏 / 完成。

    放在列表组件内部而不是各页面里：所有曲目列表共用一套，页面只要 `selectable: true`
    就自动拥有多选能力，不必每个页面各接一遍信号。
*/
Item {
    id: control
    objectName: "trackSelectionBar"

    property bool selectionMode: false
    property int selectedCount: 0
    //: 列表里的曲目总数（「全选 / 取消全选」按它判断当前状态）
    property int totalCount: 0
    property bool showSelectAll: true

    signal modeRequested
    signal selectAllRequested
    signal clearRequested
    signal downloadRequested
    signal queueRequested
    signal favoriteRequested

    implicitHeight: 30

    RowLayout {
        anchors.fill: parent
        spacing: 8

        // ── 已选提示 ────────────────────────────────────
        FluText {
            objectName: "selectionCountText"
            Layout.alignment: Qt.AlignVCenter
            visible: control.selectionMode
            text: control.selectedCount > 0 ? ("已选 " + control.selectedCount + " 首")
                                            : "点选歌曲或直接全选"
            font.pixelSize: 12
            color: control.selectedCount > 0 ? Theme.accent : Theme.textTertiary
        }

        Item { Layout.fillWidth: true }

        // ── 未进入多选 ──────────────────────────────────
        FluTextButton {
            objectName: "selectionSelectAllButton"
            Layout.alignment: Qt.AlignVCenter
            visible: !control.selectionMode && control.showSelectAll
            text: "全选"
            onClicked: control.selectAllRequested()
        }

        FluTextButton {
            objectName: "selectionModeButton"
            Layout.alignment: Qt.AlignVCenter
            visible: !control.selectionMode
            text: "多选"
            onClicked: control.modeRequested()
        }

        // ── 已进入多选 ──────────────────────────────────
        FluTextButton {
            objectName: "selectionToggleAllButton"
            Layout.alignment: Qt.AlignVCenter
            visible: control.selectionMode && control.showSelectAll
            text: control.selectedCount > 0 && control.selectedCount >= control.totalCount
                  ? "取消全选" : "全选"
            onClicked: control.selectAllRequested()
        }

        FluTextButton {
            objectName: "selectionDownloadButton"
            Layout.alignment: Qt.AlignVCenter
            visible: control.selectionMode
            text: "下载…"
            disabled: control.selectedCount === 0
            onClicked: control.downloadRequested()
        }

        FluTextButton {
            objectName: "selectionQueueButton"
            Layout.alignment: Qt.AlignVCenter
            visible: control.selectionMode
            text: "加入队列"
            disabled: control.selectedCount === 0
            onClicked: control.queueRequested()
        }

        FluTextButton {
            objectName: "selectionFavoriteButton"
            Layout.alignment: Qt.AlignVCenter
            visible: control.selectionMode
            text: "收藏"
            disabled: control.selectedCount === 0
            onClicked: control.favoriteRequested()
        }

        FluTextButton {
            objectName: "selectionClearButton"
            Layout.alignment: Qt.AlignVCenter
            visible: control.selectionMode
            text: "完成"
            onClicked: control.clearRequested()
        }
    }
}
