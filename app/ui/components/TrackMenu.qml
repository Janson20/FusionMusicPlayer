import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../ArtistNames.js" as ArtistNames

/*!
    曲目右键 / 更多按钮菜单。
*/
FluMenu {
    id: control

    property var trackData: null
    property bool isFavorite: false
    property var playlists: []

    readonly property var artistNames: ArtistNames.split(trackData && trackData.singer
                                                         ? trackData.singer : "")

    signal playNow
    signal playNext
    signal appendToQueue
    signal toggleFav
    signal addToPlaylist(string playlistId)
    signal viewArtist(string name)
    signal copyInfo

    width: 208

    FluMenuItem {
        text: "立即播放"
        onClicked: control.playNow()
    }
    FluMenuItem {
        text: "下一首播放"
        onClicked: control.playNext()
    }
    FluMenuItem {
        text: "添加到播放队列"
        onClicked: control.appendToQueue()
    }

    FluMenuSeparator {}

    FluMenuItem {
        text: control.isFavorite ? "取消喜欢" : "我喜欢"
        onClicked: control.toggleFav()
    }

    FluMenuItem {
        text: "添加到歌单"
        // 子菜单直接声明为 MenuItem 的孩子即可（subMenu 是只读属性）
        FluMenu {
            width: 200
            Repeater {
                model: control.playlists
                delegate: FluMenuItem {
                    required property var modelData
                    text: modelData.name
                    enabled: !modelData.system || modelData.id === "__favorites__"
                    onClicked: control.addToPlaylist(modelData.id)
                }
            }
            FluMenuSeparator { visible: control.playlists.length === 0 }
            FluMenuItem {
                text: "新建歌单并添加…"
                onClicked: control.addToPlaylist("__new__")
            }
        }
    }

    FluMenuItem {
        text: "查看歌手"
        visible: control.artistNames.length > 0
        FluMenu {
            width: 180
            Repeater {
                model: control.artistNames
                delegate: FluMenuItem {
                    required property string modelData
                    text: modelData
                    onClicked: control.viewArtist(modelData)
                }
            }
        }
    }

    FluMenuSeparator {}

    FluMenuItem {
        text: "复制歌曲信息"
        onClicked: control.copyInfo()
    }
}
