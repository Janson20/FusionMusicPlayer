import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."

/*!
    可复用的曲目列表：滚动、悬停、右键菜单、空状态、当前播放高亮、多选批量操作。

    页面只需传入 `model`（TrackListModel）并处理语义化信号；把 `selectable` 打开
    就自动拥有多选能力（选择工具条 + 勾选框 + 批量下载对话框），不必每个页面各接一遍。

    选择状态用 **uid 集合**（而不是行号）：列表重排、刷新之后选中的还是同一批歌；
    模型整表换掉（切换歌单 / 搜索新关键词）时会把不在新列表里的 uid 清掉。
*/
Item {
    id: control
    objectName: "trackListView"

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
    //: 是否启用多选（所有曲目列表都可以开；本地列表也在内 —— 本地曲目会被跳过）
    property bool selectable: false
    //: 多选模式（进入后整行点击 = 切换选中，行首出现勾选框）
    property bool selectionMode: false
    //: 已选中的 uid 列表（每次变更整体替换，QML 才能感知到变化）
    property var selectedUids: []
    //: uid → true 的字典：行里判断「我选中了吗」走它（O(1)）。
    //: 用数组 `indexOf` 的话，几千首的歌单全选之后每渲染一行都要扫一遍选中集。
    property var selectedMap: ({})
    readonly property int selectedCount: selectedUids.length

    signal trackActivated(int index)
    signal requestPlayNow(var track)
    signal requestPlayNext(var track)
    signal requestAppend(var track)
    signal requestFavorite(var track)

    /*! 批量操作（全部曲目列表共用一套，各页面按需接）。 */
    signal requestPlayMany(var tracks)
    signal requestAppendMany(var tracks)
    signal requestFavoriteMany(var tracks)
    /*! 选中集变了（宿主页可用来做联动的批量按钮）。 */
    signal selectionCountChanged
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

    // 模型换内容（切歌单 / 换关键词）后，把已经不在列表里的 uid 清掉：
    // 否则「已选 12 首」里可能混着上一个歌单的歌，批量下载会下错东西。
    onModelChanged: control.pruneSelection()
    Connections {
        target: control.model
        function onCountChanged() { control.pruneSelection() }
    }

    // ── 选择 ────────────────────────────────────────────────

    /*! 整批替换选中集（列表 + 查表字典一起更新，两者必须同步）。 */
    function applySelection(uids) {
        var list = uids || []
        var map = {}
        for (var i = 0; i < list.length; i++)
            map[list[i]] = true
        control.selectedMap = map
        control.selectedUids = list
        control.selectionCountChanged()
    }

    function isSelected(uid) {
        return control.selectedMap[uid] === true
    }

    function toggleUid(uid) {
        var list = control.selectedUids.slice()
        var at = list.indexOf(uid)
        if (at >= 0)
            list.splice(at, 1)
        else
            list.push(uid)
        control.applySelection(list)
    }

    function selectRange(fromIndex, toIndex) {
        if (!control.model)
            return
        var uids = control.model.uids()
        var low = Math.max(0, Math.min(fromIndex, toIndex))
        var high = Math.min(uids.length - 1, Math.max(fromIndex, toIndex))
        var list = control.selectedUids.slice()
        var seen = {}
        for (var k = 0; k < list.length; k++)
            seen[list[k]] = true
        for (var i = low; i <= high; i++) {
            if (!seen[uids[i]]) {
                seen[uids[i]] = true
                list.push(uids[i])
            }
        }
        control.applySelection(list)
    }

    function selectAll() {
        if (!control.model)
            return
        control.selectionMode = true
        control.applySelection(control.model.uids())
    }

    function clearSelection() {
        control.applySelection([])
        control.selectionMode = false
        anchorIndex = -1
    }

    function toggleSelectAll() {
        if (control.model && control.selectedUids.length >= control.model.count)
            control.clearSelection()
        else
            control.selectAll()
    }

    function pruneSelection() {
        if (control.selectedUids.length === 0 || !control.model)
            return
        var present = {}
        var all = control.model.uids()
        for (var i = 0; i < all.length; i++)
            present[all[i]] = true
        var kept = []
        for (var j = 0; j < control.selectedUids.length; j++) {
            if (present[control.selectedUids[j]])
                kept.push(control.selectedUids[j])
        }
        if (kept.length !== control.selectedUids.length)
            control.applySelection(kept)
    }

    /*! 选中曲目的完整字典（按列表顺序），批量下载 / 入队 / 收藏都吃它。 */
    function selectedTrackList() {
        var out = []
        if (!control.model)
            return out
        var count = control.model.count
        for (var i = 0; i < count; i++) {
            var track = control.model.get(i)
            if (track && control.isSelected(track.uid))
                out.push(track)
        }
        return out
    }

    // Shift 区间选择要用「上一次点的行」，它不该影响界面，所以只是个内部变量
    property int anchorIndex: -1

    function handleRowSelection(index, range) {
        if (!control.model)
            return
        control.selectionMode = true
        if (range && anchorIndex >= 0) {
            control.selectRange(anchorIndex, index)
            return
        }
        anchorIndex = index
        var track = control.model.get(index)
        if (track)
            control.toggleUid(track.uid)
    }

    // ── 下载 ────────────────────────────────────────────────

    /*! 打开批量下载对话框（多选或单曲「下载到下载目录」都走这里）。 */
    function openBatchDialog(tracks) {
        var list = tracks || []
        if (list.length === 0) {
            app.warn("先选中要下载的歌曲")
            return
        }
        batchDialog.openFor(list)
    }

    // ── 键盘 ────────────────────────────────────────────────
    //
    // 只在**多选模式**里主动要焦点：常驻 `focus: true` 会在页面加载时跟搜索框
    // 抢焦点（搜索页要求「打开就能打字」），而 Ctrl+A / Esc 恰恰只在多选里才有意义。
    focus: control.selectable && control.selectionMode
    Keys.onEscapePressed: function (event) {
        if (control.selectionMode) {
            control.clearSelection()
            event.accepted = true
        }
    }
    Keys.onPressed: function (event) {
        if (!control.selectable)
            return
        if (event.key === Qt.Key_A && (event.modifiers & Qt.ControlModifier)) {
            control.toggleSelectAll()
            event.accepted = true
        } else if (event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace) {
            if (control.selectionMode) {
                control.clearSelection()
                event.accepted = true
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: control.topMargin
        spacing: 4

        TrackSelectionBar {
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            visible: control.selectable && (control.selectionMode || control.model !== null)
            selectionMode: control.selectionMode
            selectedCount: control.selectedCount
            totalCount: control.model ? control.model.count : 0
            onModeRequested: control.selectionMode = true
            onSelectAllRequested: control.toggleSelectAll()
            onClearRequested: control.clearSelection()
            onDownloadRequested: control.openBatchDialog(control.selectedTrackList())
            onQueueRequested: control.requestAppendMany(control.selectedTrackList())
            onFavoriteRequested: control.requestFavoriteMany(control.selectedTrackList())
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: listView
                anchors.fill: parent
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
                    selectionMode: control.selectionMode
                    selected: control.isSelected(uid)

                    onActivated: control.trackActivated(index)
                    onSelectionRequested: function (range) {
                        control.handleRowSelection(index, range)
                    }
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
                        trackMenu.selectionCount = control.selectedCount
                        trackMenu.rowSelected = control.isSelected(uid)
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
        }
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
        // 右键 →「下载 → 某一档」：单曲另存为（用系统对话框选位置）
        onDownloadRequested: function (track, quality) {
            saveDialog.openFor(track, quality)
        }
        // 「下载选中的 N 首…」：整批走批量对话框
        onDownloadSelectionRequested: control.openBatchDialog(control.selectedTrackList())
        // 「下载到下载目录…」：只下右键的这一首，但让用户能改音质与选项
        onDownloadToFolderRequested: function (track) {
            control.openBatchDialog(track ? [track] : [])
        }
    }

    // 单曲另存为：右键子菜单选了音质之后弹系统「另存为」
    DownloadSaveDialog {
        id: saveDialog
    }

    // 批量下载：多选工具条 / 「下载到下载目录」都走它
    DownloadDialog {
        id: batchDialog
    }
}
