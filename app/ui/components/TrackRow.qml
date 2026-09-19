import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../ArtistNames.js" as ArtistNames

/*!
    曲目行：列表中的单首歌曲。

    作为 ListView delegate 使用，通过 `required property` 接收模型角色
    （`TrackListModel` 暴露 uid/name/singer/album/durationText 等）。
*/
Rectangle {
    id: control

    objectName: "trackRow"

    required property int index
    required property string uid
    required property string name
    required property string singer
    required property string album
    required property string albumId
    required property string durationText
    required property string cover
    required property string sourceText
    required property bool isLocal
    required property bool isOriginal
    required property string originalName
    required property string bestQuality
    // 推荐理由（漫游流才有，别的列表是空串）
    required property string reason
    // 供右键菜单构造完整曲目数据使用
    required property string source
    required property string songmid
    required property int interval

    property bool isCurrent: false
    property bool showCover: true
    property bool showIndex: true
    property bool showSource: true
    property bool showAlbum: true

    signal activated
    signal favoriteRequested
    signal artistRequested(string name)
    signal albumRequested(string albumId, string albumName)
    signal menuRequested(real globalX, real globalY)

    height: 52
    radius: Theme.radiusSmall
    color: {
        if (control.isCurrent)
            return Theme.accentSoft
        if (rowMouse.containsMouse)
            return Theme.cardHover
        return "transparent"
    }
    Behavior on color { ColorAnimation { duration: Theme.durationFast } }

    // 正在播放指示
    Rectangle {
        width: 3
        height: 22
        radius: 1.5
        color: Theme.accent
        visible: control.isCurrent
        anchors {
            left: parent.left
            verticalCenter: parent.verticalCenter
        }
    }

    // 整行的点击 / 右键区域。必须声明在内容之前：行里的歌手名链接要压在它
    // 上面才收得到点击（否则点歌手名会被整行的「播放」抢走）。
    MouseArea {
        id: rowMouse
        anchors.fill: parent
        anchors.rightMargin: 74
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onClicked: function (mouse) {
            if (mouse.button === Qt.LeftButton)
                control.activated()
            else
                control.menuRequested(mouse.x, mouse.y)
        }
        onDoubleClicked: control.activated()
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 8
        spacing: 12

        // ── 序号 / 封面 ─────────────────────────────────
        Item {
            Layout.preferredWidth: control.showCover ? 36 : 24
            Layout.preferredHeight: 36
            Layout.alignment: Qt.AlignVCenter

            CoverArt {
                anchors.fill: parent
                visible: control.showCover
                source: control.cover
                radiusSize: Theme.radiusSmall
            }

            FluText {
                anchors.centerIn: parent
                visible: !control.showCover || !control.showIndex
                text: String(control.index + 1)
                font.pixelSize: 12
                color: control.isCurrent ? Theme.accent : Theme.textTertiary
            }
        }

        // ── 标题 / 歌手 ─────────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 120
            spacing: 3

            RowLayout {
                Layout.fillWidth: true
                spacing: 6

                FluText {
                    text: control.name
                    font.pixelSize: 13
                    font.weight: control.isCurrent ? Font.DemiBold : Font.Normal
                    color: control.isCurrent ? Theme.accent : Theme.textPrimary
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                // 原唱徽标
                Rectangle {
                    visible: control.isOriginal
                    Layout.preferredWidth: origText.implicitWidth + 12
                    Layout.preferredHeight: 16
                    radius: 8
                    color: Theme.accentSoft
                    FluText {
                        id: origText
                        anchors.centerIn: parent
                        text: control.originalName !== "" ? ("原唱 · " + control.originalName) : "原唱"
                        font.pixelSize: 9
                        color: Theme.accent
                    }
                }

                // 推荐理由（漫游）
                Rectangle {
                    objectName: "trackRowReason"
                    visible: control.reason !== ""
                    Layout.preferredWidth: reasonText.implicitWidth + 12
                    Layout.preferredHeight: 16
                    radius: 8
                    color: Theme.dark ? "#2A2836" : "#F0EFF7"
                    FluText {
                        id: reasonText
                        anchors.centerIn: parent
                        text: control.reason
                        font.pixelSize: 9
                        color: Theme.textSecondary
                    }
                }
            }

            // 歌手名逐个可点（进歌手页），专辑名跟在后面
            RowLayout {
                Layout.fillWidth: true
                spacing: 0

                Repeater {
                    model: ArtistNames.split(control.singer)
                    delegate: FluText {
                        required property string modelData
                        required property int index

                        objectName: "trackRowArtistLink"
                        Layout.alignment: Qt.AlignVCenter
                        Layout.maximumWidth: 190
                        text: (index > 0 ? " / " : "") + modelData
                        font.pixelSize: 11
                        font.underline: artistMouse.containsMouse
                        color: artistMouse.containsMouse ? Theme.accent : Theme.textTertiary
                        elide: Text.ElideRight

                        MouseArea {
                            id: artistMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: control.artistRequested(modelData)
                        }
                    }
                }

                FluText {
                    objectName: "trackRowAlbumLink"
                    Layout.alignment: Qt.AlignVCenter
                    Layout.maximumWidth: 240
                    visible: control.showAlbum && control.album !== ""
                    text: (control.singer !== "" ? "  ·  " : "") + control.album
                    font.pixelSize: 11
                    font.underline: albumMouse.containsMouse
                    color: albumMouse.containsMouse ? Theme.accent : Theme.textTertiary
                    elide: Text.ElideRight

                    MouseArea {
                        id: albumMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: control.albumRequested(control.albumId, control.album)
                    }
                }

                Item { Layout.fillWidth: true }
            }
        }

        // ── 音源 / 音质 ─────────────────────────────────
        Rectangle {
            visible: control.showSource
            Layout.preferredWidth: srcText.implicitWidth + 14
            Layout.preferredHeight: 18
            Layout.alignment: Qt.AlignVCenter
            radius: 9
            color: Theme.dark ? "#2A2836" : "#F0EFF7"
            FluText {
                id: srcText
                anchors.centerIn: parent
                text: control.sourceText
                font.pixelSize: 10
                color: Theme.textSecondary
            }
        }

        FluText {
            visible: control.bestQuality !== "" && control.bestQuality !== "128k"
            Layout.alignment: Qt.AlignVCenter
            text: control.bestQuality === "flac" ? "无损"
                : (control.bestQuality === "flac24bit" ? "Hi-Res" : "320K")
            font.pixelSize: 10
            color: Theme.accent
        }

        FluText {
            Layout.preferredWidth: 46
            Layout.alignment: Qt.AlignVCenter
            horizontalAlignment: Text.AlignRight
            text: control.durationText
            font.pixelSize: 11
            color: Theme.textTertiary
        }

        // ── 操作 ────────────────────────────────────────
        FluIconButton {
            Layout.preferredWidth: 30
            Layout.preferredHeight: 30
            Layout.alignment: Qt.AlignVCenter
            iconSize: 14
            radius: Theme.radiusSmall
            iconSource: FluentIcons.More
            iconColor: Theme.textSecondary
            text: "更多"
            opacity: rowMouse.containsMouse || hovered ? 1 : 0
            onClicked: control.menuRequested(control.width, control.height)
        }
    }
}
