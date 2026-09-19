import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"

/*!
    漫游页：一条持续生成的个性化推荐流。

    和别的页面最大的不同是「它会一直往下续」：点开始漫游后队列快放完时
    ``RoamController`` 会自动再取一批塞进队列（时机见 core/roam.py），
    所以这里既是「推荐流列表」，也是「电台」。
*/
Item {
    id: control

    objectName: "roamPage"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 14

        // ── 顶部：标题 + 操作 ───────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            ColumnLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: 2

                RowLayout {
                    spacing: 8

                    FluText {
                        text: "漫游"
                        font.pixelSize: 20
                        font.weight: Font.Bold
                        color: Theme.textPrimary
                    }

                    Rectangle {
                        Layout.alignment: Qt.AlignVCenter
                        visible: roam.active
                        width: roamActiveText.implicitWidth + 16
                        height: 20
                        radius: 10
                        color: Theme.accentSoft
                        FluText {
                            id: roamActiveText
                            anchors.centerIn: parent
                            text: "漫游中"
                            font.pixelSize: 10
                            color: Theme.accent
                        }
                    }
                }

                FluText {
                    text: roam.hint + (account.loggedIn ? "" : "（登录后按你的口味推荐）")
                    font.pixelSize: 11
                    color: Theme.textTertiary
                }
            }

            Item { Layout.fillWidth: true }

            FluProgressRing {
                Layout.preferredWidth: 20
                Layout.preferredHeight: 20
                Layout.alignment: Qt.AlignVCenter
                strokeWidth: 3
                visible: roam.loading
            }

            FluButton {
                objectName: "roamRefreshButton"
                Layout.alignment: Qt.AlignVCenter
                text: "换一批"
                disabled: roam.loading
                onClicked: roam.refresh()
            }

            FluButton {
                objectName: "roamMoreButton"
                Layout.alignment: Qt.AlignVCenter
                text: "再多来点"
                disabled: roam.loading
                onClicked: roam.more()
            }

            FluFilledButton {
                objectName: "roamStartButton"
                Layout.alignment: Qt.AlignVCenter
                text: roam.active ? "重新漫游" : "开始漫游"
                disabled: roam.count === 0
                onClicked: roam.start()
            }
        }

        // ── 推荐流 ──────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border
            clip: true

            TrackListView {
                objectName: "roamList"
                anchors.fill: parent
                anchors.margins: 6
                model: roam.model
                busy: roam.loading
                showCover: true
                emptyIcon: FluentIcons.MapCompassTop
                emptyTitle: roam.loading ? "正在为你挑选…" : "还没有推荐"
                emptyDescription: roam.loading ? "" : "点「换一批」让漫游开始挑歌"
                emptyActionText: roam.loading ? "" : "换一批"
                onEmptyActionTriggered: roam.refresh()
                onTrackActivated: function (index) { roam.playFrom(index) }
                onRequestPlayNow: function (track) { player.playTrack(track) }
                onRequestPlayNext: function (track) { player.playNextTrack(track) }
                onRequestAppend: function (track) { player.appendToQueue(track) }
                onRequestFavorite: function (track) { library.toggleFavorite(track) }
            }
        }

        // ── 底部：续歌控制 ──────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 34 : 0
            visible: roam.active
            spacing: 10

            FluText {
                Layout.alignment: Qt.AlignVCenter
                text: "漫游会一直续下去，直到你播放别的歌"
                font.pixelSize: 11
                color: Theme.textTertiary
            }

            Item { Layout.fillWidth: true }

            FluTextButton {
                objectName: "roamStopButton"
                text: "停止续歌"
                onClicked: roam.stop()
            }
        }
    }

    // 切到本页时才取第一批：StackLayout 里的页面在启动时就都建好了，
    // 如果在 onCompleted 里取，会赶在 account.restore() 之前发请求 ——
    // 那时会话里还没有登录 Cookie，私人 FM 只会退化成「新歌推荐」。
    onVisibleChanged: {
        if (visible && roam.count === 0 && !roam.loading && !roam.requested)
            roam.refresh()
    }

    Component.onCompleted: {
        if (visible && roam.count === 0 && !roam.loading && !roam.requested)
            roam.refresh()
    }
}
