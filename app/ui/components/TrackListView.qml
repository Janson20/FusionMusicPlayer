import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    可复用的曲目列表：滚动、悬停、右键菜单、空状态、当前播放高亮。

    页面只需传入 `model`（TrackListModel）并处理语义化信号。
*/
Item {
    id: control

    property var model: null
    property bool showCover: true
    property bool showIndex: true
    property bool showSource: true
    property bool showAlbum: true
    property bool busy: false
    property string emptyIcon: ""
    property string emptyTitle: "这里还没有歌曲"
    property string emptyDescription: ""
    property string emptyActionText: ""
    property int topMargin: 0

    signal trackActivated(int index)
    signal requestPlayNow(var track)
    signal requestPlayNext(var track)
    signal requestAppend(var track)
    signal requestFavorite(var track)
    signal artistRequested(string name)
    signal albumRequested(string albumId, string albumName)
    signal emptyActionTriggered

    clip: true

    // 行里的歌手名 / 专辑名（或右键菜单的同名入口）点了就进对应的详情页。
    // 放在这里而不是各个页面里，是为了「所有地方点歌手名 / 专辑名都能进」。
    onArtistRequested: function (name) { artist.openByName(name) }
    onAlbumRequested: function (albumId, albumName) {
        album.openById(albumId, albumName)
    }

    ListView {
        id: listView
        anchors.fill: parent
        anchors.topMargin: control.topMargin
        visible: control.model !== null && control.model.count > 0

        model: control.model
        spacing: 2
        cacheBuffer: 800
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        reuseItems: true

        ScrollBar.vertical: FluScrollBar { }

        delegate: TrackRow {
            width: listView.width
            isCurrent: player.currentTrack ? player.currentTrack.uid === uid : false
            showCover: control.showCover
            showIndex: control.showIndex
            showSource: control.showSource
            showAlbum: control.showAlbum

            onActivated: control.trackActivated(index)
            onArtistRequested: function (name) { control.artistRequested(name) }
            onAlbumRequested: function (albumId, albumName) {
                control.albumRequested(albumId, albumName)
            }
            onMenuRequested: function (x, y) {
                // 用模型行取完整字典：QML 里手拼的 JS 对象会丢掉 types/type_detail，
                // 那样入库后恢复播放会退化成 128k
                trackMenu.trackData = control.model ? control.model.get(index) : null
                trackMenu.isFavorite = trackMenu.trackData
                    ? library.isFavorite(trackMenu.trackData) : false
                trackMenu.playlists = library.playlists
                trackMenu.popup()
            }
        }

        add: Transition {
            NumberAnimation { properties: "opacity"; from: 0; to: 1; duration: Theme.durationNormal }
        }
    }

    EmptyState {
        anchors.fill: parent
        visible: !control.busy && (control.model === null || control.model.count === 0)
        busy: control.busy
        iconSource: control.emptyIcon !== "" ? control.emptyIcon : FluentIcons.MusicNote
        title: control.emptyTitle
        description: control.emptyDescription
        actionText: control.emptyActionText
        onActionTriggered: control.emptyActionTriggered()
    }

    TrackMenu {
        id: trackMenu
        onPlayNow: control.requestPlayNow(trackMenu.trackData)
        onPlayNext: control.requestPlayNext(trackMenu.trackData)
        onAppendToQueue: control.requestAppend(trackMenu.trackData)
        onToggleFav: control.requestFavorite(trackMenu.trackData)
        onViewArtist: function (name) { control.artistRequested(name) }
        onViewAlbum: function (albumId, albumName) {
            control.albumRequested(albumId, albumName)
        }
        onCopyInfo: {
            var t = trackMenu.trackData
            if (t)
                settings.copyToClipboard(t.name + " - " + t.singer)
        }
        onAddToPlaylist: function (playlistId) {
            if (!trackMenu.trackData)
                return
            if (playlistId === "__new__") {
                library.createPlaylist("新建歌单")
                var list = library.playlists
                if (list.length > 0)
                    library.addToPlaylist(list[list.length - 1].id, trackMenu.trackData)
            } else {
                library.addToPlaylist(playlistId, trackMenu.trackData)
            }
        }
    }
}
