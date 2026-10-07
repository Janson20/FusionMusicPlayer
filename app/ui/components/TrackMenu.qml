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
    //: 宿主列表里当前选中的数量（0 = 没在多选；>0 时菜单里多一条批量入口）
    property int selectionCount: 0
    //: 右键点的这一行是否在选中集里（决定「下载选中的 N 首」出不出现）
    property bool rowSelected: false

    readonly property var artistNames: ArtistNames.split(trackData && trackData.singer
                                                         ? trackData.singer : "")
    readonly property string albumName: trackData && trackData.album ? String(trackData.album) : ""
    readonly property string albumId: trackData && trackData.album_id
        ? String(trackData.album_id) : ""
    readonly property bool downloadable: !!trackData && !trackData.isLocal
        && String(trackData.songmid || "") !== ""
    //: 音质选项（含「该音源有没有这一档」与预计体积），打开菜单时算一次
    readonly property var qualityChoices: downloadable
        ? download.qualityOptions(trackData) : []

    signal playNow
    signal playNext
    signal appendToQueue
    signal toggleFav
    signal addToPlaylist(string playlistId)
    signal viewArtist(string name)
    signal viewAlbum(string albumId, string albumName)
    signal copyInfo
    //: 下载单曲（quality 为档位 id，空串表示用设置里的默认档）
    signal downloadRequested(var track, string quality)
    //: 下载当前多选的全部曲目
    signal downloadSelectionRequested
    //: 只把右键这一首下载到下载目录（音质与选项在对话框里定）
    signal downloadToFolderRequested(var track)

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

    FluMenuSeparator {}

    // 多选里右键：先给批量入口（这时用户多半是想整批下载）
    FluMenuItem {
        objectName: "trackMenuDownloadSelection"
        visible: control.rowSelected && control.selectionCount > 1
        text: "下载选中的 " + control.selectionCount + " 首…"
        onClicked: control.downloadSelectionRequested()
    }

    FluMenuItem {
        objectName: "trackMenuDownload"
        text: "下载"
        enabled: control.downloadable
        // 本地曲目没有可下载的东西，禁掉并说明，而不是点了没反应
        FluMenu {
            width: 250
            FluMenuItem {
                objectName: "trackMenuDownloadDefault"
                text: "按默认音质另存为（" + download.qualityLabel(download.defaults().quality) + "）…"
                onClicked: control.downloadRequested(control.trackData, "")
            }
            FluMenuSeparator {}
            Repeater {
                model: control.qualityChoices
                delegate: FluMenuItem {
                    required property var modelData
                    text: modelData.name
                          + (modelData.sizeText !== "" ? "（约 " + modelData.sizeText + "）" : "")
                          + (modelData.available ? "" : " · 该音源无此档")
                    onClicked: control.downloadRequested(control.trackData, modelData.id)
                }
            }
            FluMenuSeparator {}
            FluMenuItem {
                text: "下载到下载目录…"
                onClicked: control.downloadToFolderRequested(control.trackData)
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

    FluMenuItem {
        text: control.albumName !== "" ? ("查看专辑 · " + control.albumName) : "查看专辑"
        visible: control.albumName !== ""
        enabled: control.albumId !== "" || control.albumName !== ""
        onClicked: control.viewAlbum(control.albumId, control.albumName)
    }

    FluMenuSeparator {}

    FluMenuItem {
        text: "复制歌曲信息"
        onClicked: control.copyInfo()
    }
}
