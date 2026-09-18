import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    网易云登录窗口：扫码 / 手机验证码 / 手机密码 / 粘贴 Cookie。
*/
FluWindow {
    id: window

    width: 720
    height: 520
    minimumWidth: 700
    minimumHeight: 500
    title: "登录网易云音乐"
    visible: false
    // 关闭时只隐藏、不销毁（原因同 SettingsWindow.qml）
    closeDestory: false
    showStayTop: false
    showDark: false
    showMaximize: false
    fixSize: true

    // 抵消 FluWindow 基类 Component.onCompleted 里的无条件 show()
    Component.onCompleted: hide()

    property int method: 0   // 0 扫码 / 1 手机 / 2 Cookie
    property string phone: ""
    property string secret: ""
    property bool usePassword: false

    function showWindow() {
        window.visible = true
        window.requestActivate()
        if (account.loggedIn)
            return
        account.startQrLogin()
    }

    onVisibleChanged: {
        if (!visible)
            account.cancelQrLogin()
    }

    // 登录成功后自动关闭
    Connections {
        target: account
        function onLoggedInChanged() {
            if (account.loggedIn)
                Qt.callLater(function () { window.visible = false })
        }
    }

    Item {
        anchors.fill: parent

        // ── 左侧：品牌区 ────────────────────────────────────
        Rectangle {
            id: brandPanel
            anchors {
                left: parent.left
                top: parent.top
                bottom: parent.bottom
            }
            width: 268

            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: Theme.accent }
                GradientStop { position: 1.0; color: Theme.accentGradientEnd }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 28
                spacing: 14

                FluIcon {
                    Layout.alignment: Qt.AlignLeft
                    iconSource: FluentIcons.MusicNote
                    iconSize: 40
                    iconColor: "#FFFFFF"
                }

                FluText {
                    Layout.fillWidth: true
                    text: "Fusion Music Player"
                    font.pixelSize: 19
                    font.weight: Font.Bold
                    color: "#FFFFFF"
                    wrapMode: Text.WordWrap
                }

                FluText {
                    Layout.fillWidth: true
                    text: "登录网易云音乐账号"
                    font.pixelSize: 13
                    color: Qt.rgba(1, 1, 1, 0.85)
                }

                Item { Layout.preferredHeight: 8 }

                Repeater {
                    model: [
                        "解锁无损 / Hi-Res 音质",
                        "同步「我喜欢的音乐」与自建歌单",
                        "获取官方翻译歌词与罗马音",
                        "每日推荐与个性化歌单"
                    ]
                    delegate: RowLayout {
                        required property string modelData
                        Layout.fillWidth: true
                        spacing: 8
                        FluIcon {
                            Layout.alignment: Qt.AlignTop
                            iconSource: FluentIcons.CheckMark
                            iconSize: 12
                            iconColor: Qt.rgba(1, 1, 1, 0.9)
                        }
                        FluText {
                            Layout.fillWidth: true
                            text: modelData
                            font.pixelSize: 12
                            color: Qt.rgba(1, 1, 1, 0.88)
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Qt.rgba(1, 1, 1, 0.25)
                }
                FluText {
                    Layout.fillWidth: true
                    text: "凭据以 AES-256-GCM 加密保存在程序目录，不会上传到任何第三方。"
                    font.pixelSize: 10
                    color: Qt.rgba(1, 1, 1, 0.7)
                    wrapMode: Text.WordWrap
                }
            }
        }

        // ── 右侧：登录方式 ──────────────────────────────────
        ColumnLayout {
            anchors {
                left: brandPanel.right
                right: parent.right
                top: parent.top
                bottom: parent.bottom
                margins: 24
            }
            spacing: 16

            // 已登录态
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: account.loggedIn
                spacing: 14

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 76
                    Layout.preferredHeight: 76
                    radius: 38
                    color: Theme.accentSoft
                    clip: true
                    Image {
                        anchors.fill: parent
                        source: account.avatar
                        visible: account.avatar !== ""
                        fillMode: Image.PreserveAspectCrop
                        sourceSize.width: 160
                        sourceSize.height: 160
                    }
                    FluIcon {
                        anchors.centerIn: parent
                        visible: account.avatar === ""
                        iconSource: FluentIcons.Accounts
                        iconSize: 32
                        iconColor: Theme.accent
                    }
                }

                FluText {
                    Layout.alignment: Qt.AlignHCenter
                    text: "已登录：" + (account.nickname || "网易云用户")
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                    color: Theme.textPrimary
                }
                FluText {
                    Layout.alignment: Qt.AlignHCenter
                    text: account.vipLabel
                    font.pixelSize: 12
                    color: Theme.accent
                }

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 10
                    FluButton {
                        text: "刷新账号信息"
                        onClicked: account.refresh()
                    }
                    FluButton {
                        text: "退出登录"
                        onClicked: account.logout()
                    }
                }

                Item { Layout.fillHeight: true }
            }

            // 未登录态
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: !account.loggedIn
                spacing: 14

                RowLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 6

                    Repeater {
                        model: ["扫码登录", "手机号", "Cookie"]
                        delegate: Rectangle {
                            required property string modelData
                            required property int index
                            width: Math.max(84, labelText.implicitWidth + 28)
                            height: 32
                            radius: 16
                            color: window.method === index
                                ? Theme.accent
                                : (methodMouse.containsMouse ? Theme.accentSoft
                                   : (Theme.dark ? "#252431" : "#F0EFF7"))
                            Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                            FluText {
                                id: labelText
                                anchors.centerIn: parent
                                text: modelData
                                font.pixelSize: 12
                                font.weight: window.method === index ? Font.DemiBold : Font.Normal
                                color: window.method === index ? Theme.accentText : Theme.textSecondary
                            }

                            MouseArea {
                                id: methodMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: {
                                    window.method = index
                                    if (index === 0)
                                        account.startQrLogin()
                                    else
                                        account.cancelQrLogin()
                                }
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }
                }

                // ── 扫码 ────────────────────────────────────
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: window.method === 0
                    spacing: 12

                    Item { Layout.fillHeight: true }

                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 204
                        height: 204
                        radius: Theme.radius
                        color: "#FFFFFF"
                        border.width: 1
                        border.color: Theme.border

                        Image {
                            anchors.centerIn: parent
                            width: 188
                            height: 188
                            source: account.qrImage
                            visible: account.qrImage !== ""
                            fillMode: Image.PreserveAspectFit
                            cache: false
                            sourceSize.width: 376
                            sourceSize.height: 376
                        }

                        FluProgressRing {
                            anchors.centerIn: parent
                            width: 34
                            height: 34
                            strokeWidth: 4
                            visible: account.qrImage === ""
                        }
                    }

                    FluText {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillWidth: true
                        text: account.status
                        font.pixelSize: 12
                        color: Theme.textSecondary
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    FluButton {
                        Layout.alignment: Qt.AlignHCenter
                        text: "刷新二维码"
                        disabled: account.busy && account.qrImage !== ""
                        onClicked: account.startQrLogin()
                    }

                    Item { Layout.fillHeight: true }
                }

                // ── 手机号 ──────────────────────────────────
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: window.method === 1
                    spacing: 12

                    Item { Layout.fillHeight: true }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 8
                        FluTextBox {
                            id: phoneBox
                            Layout.preferredWidth: 220
                            placeholderText: "手机号"
                            onTextChanged: window.phone = text
                        }
                        FluButton {
                            text: "发送验证码"
                            disabled: account.busy
                            onClicked: account.sendCaptcha(phoneBox.text, "86")
                        }
                    }

                    FluTextBox {
                        id: secretBox
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 320
                        placeholderText: window.usePassword ? "密码" : "短信验证码"
                        onTextChanged: window.secret = text
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 8
                        FluCheckBox {
                            text: "使用密码登录"
                            checked: window.usePassword
                            clickListener: function () { window.usePassword = !window.usePassword }
                        }
                    }

                    FluFilledButton {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 320
                        text: account.busy ? "登录中…" : "登录"
                        disabled: account.busy
                        onClicked: account.loginWithPhone(phoneBox.text, secretBox.text, "86",
                                                          window.usePassword)
                    }

                    FluText {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillWidth: true
                        Layout.maximumWidth: 360
                        text: window.usePassword
                            ? "网易已逐步下线密码登录，若提示「请切换登录方式」请改用扫码或短信验证码。"
                            : "验证码由网易云官方短信下发，程序不会保存你的手机号。"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    Item { Layout.fillHeight: true }
                }

                // ── Cookie ──────────────────────────────────
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: window.method === 2
                    spacing: 12

                    Item { Layout.fillHeight: true }

                    FluText {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.fillWidth: true
                        Layout.maximumWidth: 400
                        text: "粘贴从浏览器或其它工具获取的网易云 Cookie（至少包含 MUSIC_U）"
                        font.pixelSize: 11
                        color: Theme.textTertiary
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                    }

                    FluMultilineTextBox {
                        id: cookieBox
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 400
                        Layout.preferredHeight: 110
                        placeholderText: "MUSIC_U=...; __csrf=..."
                    }

                    FluFilledButton {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 400
                        text: "验证并登录"
                        disabled: account.busy
                        onClicked: account.loginWithCookie(cookieBox.text)
                    }

                    Item { Layout.fillHeight: true }
                }

                FluText {
                    Layout.fillWidth: true
                    visible: window.method !== 0
                    text: account.status
                    font.pixelSize: 11
                    color: Theme.accent
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
