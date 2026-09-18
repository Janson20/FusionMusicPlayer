import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    标题栏：应用标识 + 设置按钮 + 系统窗口按钮。

    直接复用 FluentUI 的 FluAppBar（它已经处理好拖拽、双击最大化、右键系统菜单），
    只在右侧插入一个设置按钮。由于 `showDark`/`showStayTop` 均为 false，
    右侧系统按钮行固定为 3 × 40 = 120px，因此设置按钮以 120px 右边距紧贴其左侧。
*/
FluAppBar {
    id: control

    readonly property int systemButtonsWidth: 120

    title: ""
    showDark: false
    showStayTop: false
    showClose: true
    showMinimize: true
    showMaximize: true
    titleVisible: false

    signal settingsClicked

    // ── 左侧：品牌标识 ──────────────────────────────────
    RowLayout {
        anchors {
            left: parent.left
            leftMargin: 16
            verticalCenter: parent.verticalCenter
        }
        spacing: 9

        Rectangle {
            Layout.preferredWidth: 20
            Layout.preferredHeight: 20
            radius: 6
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.accent }
                GradientStop { position: 1.0; color: Theme.accentGradientEnd }
            }
            FluIcon {
                anchors.centerIn: parent
                iconSource: FluentIcons.MusicNote
                iconSize: 11
                iconColor: Theme.accentText
            }
        }

        FluText {
            text: "Fusion Music Player"
            font.pixelSize: 12
            font.weight: Font.DemiBold
            color: Theme.textSecondary
            Layout.alignment: Qt.AlignVCenter
        }
    }

    // ── 右侧：设置按钮（草图里的「设置按钮」）─────────────
    FluIconButton {
        id: btnSettings
        anchors {
            right: parent.right
            rightMargin: control.systemButtonsWidth
            verticalCenter: parent.verticalCenter
        }
        width: 40
        height: 30
        radius: 0
        iconSize: 15
        iconSource: FluentIcons.Settings
        iconColor: control.textColor
        text: "设置"
        onClicked: control.settingsClicked()
    }
}
