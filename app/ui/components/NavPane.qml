import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    左侧标签页导航（对应草图中的「标签页」列）。

    自绘而非使用 FluNavigationView：后者绑定自己的 StackView 页面注册体系，
    本应用的页面切换由 Main.qml 的 StackLayout 统一管理，自绘更直接也更好控制样式。
*/
Rectangle {
    id: control

    property string currentPage: "discover"
    property bool expanded: true
    property int favoriteCount: 0
    property int historyCount: 0
    property int localCount: 0

    signal pageRequested(string pageId)
    signal loginRequested

    color: Theme.navBg
    implicitWidth: expanded ? Theme.navWidth : Theme.navCompactWidth

    Behavior on implicitWidth {
        NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutCubic }
    }

    // 导航项定义
    readonly property var items: [
        { id: "discover", name: "发现音乐", icon: FluentIcons.Globe,  badge: 0 },
        { id: "roam",     name: "漫游",     icon: FluentIcons.MapCompassTop, badge: 0 },
        { id: "search",   name: "搜索",     icon: FluentIcons.Search, badge: 0 },
        { id: "library",  name: "我的音乐", icon: FluentIcons.Heart,  badge: favoriteCount },
        { id: "local",    name: "本地音乐", icon: FluentIcons.Folder, badge: localCount },
        { id: "queue",    name: "播放队列", icon: FluentIcons.List,   badge: 0 }
    ]

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 10
        anchors.bottomMargin: 10
        spacing: 0

        Repeater {
            model: control.items

            delegate: Item {
                id: navItem
                required property var modelData

                Layout.fillWidth: true
                Layout.preferredHeight: 44
                Layout.leftMargin: 8
                Layout.rightMargin: 8

                readonly property bool active: control.currentPage === modelData.id
                readonly property bool hovered: mouseArea.containsMouse

                Rectangle {
                    id: bg
                    anchors.fill: parent
                    radius: Theme.radius
                    color: navItem.active
                        ? Theme.accentSoft
                        : (navItem.hovered ? FluTheme.itemHoverColor : "transparent")

                    Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                    // 选中指示条
                    Rectangle {
                        width: 3
                        height: 18
                        radius: 1.5
                        color: Theme.accent
                        anchors {
                            left: parent.left
                            leftMargin: 1
                            verticalCenter: parent.verticalCenter
                        }
                        opacity: navItem.active ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }
                    }
                }

                FluIcon {
                    id: icon
                    iconSource: navItem.modelData.icon
                    iconSize: 16
                    iconColor: navItem.active ? Theme.accent : Theme.textSecondary
                    anchors {
                        left: parent.left
                        leftMargin: control.expanded ? 16 : 0
                        verticalCenter: parent.verticalCenter
                        horizontalCenter: control.expanded ? undefined : parent.horizontalCenter
                    }
                }

                FluText {
                    text: navItem.modelData.name
                    font.pixelSize: 13
                    font.weight: navItem.active ? Font.DemiBold : Font.Normal
                    color: navItem.active ? Theme.accent : Theme.textPrimary
                    visible: control.expanded
                    anchors {
                        left: icon.right
                        leftMargin: 12
                        verticalCenter: parent.verticalCenter
                    }
                }

                // 数量徽标
                Rectangle {
                    visible: control.expanded && navItem.modelData.badge > 0
                    width: Math.max(20, badgeText.implicitWidth + 10)
                    height: 17
                    radius: 9
                    color: navItem.active ? Theme.accent : FluTheme.itemCheckColor
                    anchors {
                        right: parent.right
                        rightMargin: 12
                        verticalCenter: parent.verticalCenter
                    }
                    FluText {
                        id: badgeText
                        anchors.centerIn: parent
                        text: navItem.modelData.badge > 999 ? "999+" : String(navItem.modelData.badge)
                        font.pixelSize: 10
                        color: navItem.active ? Theme.accentText : Theme.textSecondary
                    }
                }

                FluTooltip {
                    visible: !control.expanded && mouseArea.containsMouse
                    text: navItem.modelData.name
                    delay: 400
                }

                MouseArea {
                    id: mouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: control.pageRequested(navItem.modelData.id)
                }
            }
        }

        Item { Layout.fillHeight: true }

        // ── 底部：账号入口 + 折叠按钮 ────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.leftMargin: 18
            Layout.rightMargin: 18
            Layout.bottomMargin: 8
            color: Theme.divider
        }

        Rectangle {
            id: accountButton
            Layout.fillWidth: true
            Layout.preferredHeight: 46
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            Layout.bottomMargin: 4
            radius: Theme.radius
            color: accountMouse.containsMouse ? FluTheme.itemHoverColor : "transparent"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: control.expanded ? 10 : 0
                anchors.rightMargin: control.expanded ? 10 : 0
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 26
                    Layout.preferredHeight: 26
                    Layout.alignment: Qt.AlignVCenter | (control.expanded ? Qt.AlignLeft : Qt.AlignHCenter)
                    radius: 13
                    color: Theme.accentSoft
                    clip: true

                    Image {
                        anchors.fill: parent
                        source: account.loggedIn ? account.avatar : ""
                        visible: account.loggedIn && account.avatar !== ""
                        fillMode: Image.PreserveAspectCrop
                        sourceSize.width: 64
                        sourceSize.height: 64
                    }
                    FluIcon {
                        anchors.centerIn: parent
                        visible: !account.loggedIn || account.avatar === ""
                        iconSource: account.loggedIn ? FluentIcons.Contact : FluentIcons.Accounts
                        iconSize: 14
                        iconColor: Theme.accent
                    }
                }

                ColumnLayout {
                    visible: control.expanded
                    Layout.fillWidth: true
                    spacing: 1
                    FluText {
                        text: account.loggedIn ? (account.nickname || "已登录") : "未登录"
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        color: Theme.textPrimary
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    FluText {
                        text: account.loggedIn ? account.vipLabel : "点击登录网易云"
                        font.pixelSize: 10
                        color: Theme.textTertiary
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
            }

            FluTooltip {
                visible: !control.expanded && accountMouse.containsMouse
                text: account.loggedIn ? (account.nickname || "已登录") : "登录网易云"
                delay: 400
            }

            MouseArea {
                id: accountMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: control.loginRequested()
            }
        }
    }
}
