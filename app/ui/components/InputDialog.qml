import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    通用文本输入对话框。

    没有直接用 FluContentDialog：它的 contentDelegate 是 Component，
    内部控件 id 无法从外部访问，读取输入值很别扭。这里自建 Popup，
    对「取回用户输入」这件事更直接。
*/
Popup {
    id: dialog

    property string title: "输入"
    property string label: ""
    property string placeholder: ""
    property string text: ""
    property bool multiline: false
    property string hint: ""
    property bool usePasswordMask: false

    signal accepted(string value)
    signal cancelled

    function openWith(initialText) {
        dialog.text = initialText !== undefined && initialText !== null ? initialText : ""
        dialog.open()
        Qt.callLater(function () { dialog.multiline ? fieldMulti.forceActiveFocus()
                                                   : fieldSingle.forceActiveFocus() })
    }

    function currentText() {
        return dialog.multiline ? fieldMulti.text : fieldSingle.text
    }

    anchors.centerIn: Overlay.overlay
    width: 400
    padding: 0
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape

    Overlay.modal: Rectangle { color: Theme.scrim }

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durationFast }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.durationFast }
    }

    background: Rectangle {
        color: Theme.overlayBg
        radius: Theme.radiusLarge
        border.width: 1
        border.color: Theme.border
        FluShadow { radius: Theme.radiusLarge }
    }

    contentItem: ColumnLayout {
        spacing: 0

        FluText {
            Layout.fillWidth: true
            Layout.topMargin: 20
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            text: dialog.title
            font.pixelSize: 16
            font.weight: Font.DemiBold
            color: Theme.textPrimary
            wrapMode: Text.WrapAnywhere
        }

        FluText {
            Layout.fillWidth: true
            Layout.topMargin: dialog.label !== "" ? 12 : 0
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            visible: dialog.label !== ""
            text: dialog.label
            font.pixelSize: 12
            color: Theme.textSecondary
            wrapMode: Text.WordWrap
        }

        FluTextBox {
            id: fieldSingle
            Layout.fillWidth: true
            Layout.topMargin: 14
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            visible: !dialog.multiline
            placeholderText: dialog.placeholder
            onCommit: dialog.accept()
        }

        FluMultilineTextBox {
            id: fieldMulti
            Layout.fillWidth: true
            Layout.topMargin: 14
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            Layout.preferredHeight: 108
            visible: dialog.multiline
            placeholderText: dialog.placeholder
            isCtrlEnterForNewline: true
        }

        FluText {
            Layout.fillWidth: true
            Layout.topMargin: 10
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            visible: dialog.hint !== ""
            text: dialog.hint
            font.pixelSize: 11
            color: Theme.textTertiary
            wrapMode: Text.WordWrap
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 20
            Layout.bottomMargin: 16
            Layout.leftMargin: 22
            Layout.rightMargin: 22
            spacing: 10

            Item { Layout.fillWidth: true }

            FluButton {
                text: "取消"
                onClicked: {
                    dialog.cancelled()
                    dialog.close()
                }
            }

            FluFilledButton {
                text: "确定"
                onClicked: dialog.accept()
            }
        }
    }

    onOpened: {
        if (dialog.multiline)
            fieldMulti.text = dialog.text
        else
            fieldSingle.text = dialog.text
    }

    function accept() {
        dialog.accepted(dialog.currentText().trim())
        dialog.close()
    }
}
