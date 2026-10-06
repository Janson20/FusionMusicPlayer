import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import FluentUI
import ".."
import "../components"
import "../ArtistNames.js" as ArtistNames

/*!
    搜索页：多音源并发搜索 + 来源筛选 + 分页。

    「全部」标签页顶部按网易云的样式置顶一张歌手卡片和一张歌单卡片
    （``search.topArtist`` / ``search.topPlaylist``），点了直接进歌手页 / 歌单页。

    搜索框下方挂**联想词**（``search.suggestions``）：数据来自网易云的
    「猜你想搜」（``netease.search_suggest``），前几条可能是本地历史命中
    （打第一个字就有东西可点，且不联网）。上下键选、回车搜、Esc 收，
    鼠标移上去也会跟着高亮。
*/
Item {
    id: control
    objectName: "searchPage"

    readonly property var tabs: search.sourceTabs
    readonly property bool showTops: search.currentSource === "all"
        && (control.hasArtistCard || control.hasPlaylistCard)
    readonly property bool hasArtistCard: search.topArtist.id !== undefined
        && search.topArtist.id !== ""
    readonly property bool hasPlaylistCard: search.topPlaylist.id !== undefined
        && search.topPlaylist.id !== ""

    // ── 联想状态 ────────────────────────────────────────────
    //: 当前高亮的联想项（-1 = 没选中，回车搜输入框里的原文）
    property int suggestIndex: -1
    //: 用户主动收起过（Esc / 已经搜过了），输入框再有变化才会重新弹
    property bool suggestDismissed: false

    readonly property var suggestItems: search.suggestions
    readonly property bool suggestVisible: searchBox.activeFocus && !control.suggestDismissed
        && searchBox.text.trim() !== "" && control.suggestItems.length > 0
        && !search.loading

    function suggestKeyword(index) {
        var items = control.suggestItems
        if (index < 0 || index >= items.length)
            return ""
        return String(items[index].keyword)
    }

    //: 上下键移动高亮（到边界停住，不循环 —— 循环会让人不知道自己在第几条）
    function moveSuggest(delta) {
        if (!control.suggestVisible)
            return
        var count = control.suggestItems.length
        var next = control.suggestIndex + delta
        if (control.suggestIndex < 0)
            next = delta > 0 ? 0 : count - 1
        control.suggestIndex = Math.max(0, Math.min(count - 1, next))
    }

    //: 回车 / 点「搜索」：选中了联想词就搜它，否则搜输入框里的原文
    function submitSearch() {
        var word = control.suggestKeyword(control.suggestIndex)
        if (word === "")
            word = searchBox.text.trim()
        if (word === "")
            return
        control.applyKeyword(word)
    }

    function applyKeyword(word) {
        control.suggestDismissed = true
        control.suggestIndex = -1
        searchBox.text = word          // 程序改 text 不触发 textEdited，联想不会自己弹回来
        search.search(word)
    }

    function doSearch() {
        control.submitSearch()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 14

        // ── 搜索框 ──────────────────────────────────────────
        // z 要高过下面的结果卡片：联想下拉挂在这一行里的搜索框身上（见文件末尾），
        // 不抬高层级的话它会被稍后声明的卡片盖住 —— 位置对了却看不见
        RowLayout {
            id: searchRow
            z: 50
            Layout.fillWidth: true
            spacing: 10

            FluTextBox {
                id: searchBox
                objectName: "searchInput"
                Layout.fillWidth: true
                Layout.maximumWidth: 560
                placeholderText: "搜索歌曲、歌手、专辑（网易云 / QQ / 酷我 / 酷狗 / 咪咕）"
                iconSource: FluentIcons.Search
                cleanEnabled: true

                // 打字 → 问联想（防抖与去重都在 Python 侧）
                onTextEdited: {
                    control.suggestDismissed = false
                    control.suggestIndex = -1
                    search.suggest(text)
                }
                onActiveFocusChanged: {
                    if (activeFocus && !control.suggestDismissed && text.trim() !== "")
                        search.suggest(text)     // 重新聚焦时把上次的联想捞回来
                }

                Keys.onDownPressed: function (event) {
                    control.moveSuggest(1)
                    event.accepted = true
                }
                Keys.onUpPressed: function (event) {
                    control.moveSuggest(-1)
                    event.accepted = true
                }
                Keys.onEscapePressed: function (event) {
                    control.suggestDismissed = true
                    control.suggestIndex = -1
                    search.clearSuggestions()
                    event.accepted = true
                }
                Keys.onReturnPressed: function (event) {
                    control.submitSearch()
                    event.accepted = true
                }
                onCommit: control.submitSearch()
            }

            FluFilledButton {
                text: "搜索"
                disabled: search.loading
                onClicked: control.doSearch()
            }

            Item { Layout.fillWidth: true }

            FluProgressRing {
                Layout.preferredWidth: 22
                Layout.preferredHeight: 22
                Layout.alignment: Qt.AlignVCenter
                strokeWidth: 3
                visible: search.loading
            }
        }

        // ── 搜索历史（无结果时）────────────────────────────
        Flow {
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? implicitHeight : 0
            visible: !search.hasResults && !search.loading && search.history.length > 0
            spacing: 8

            FluText {
                text: "最近搜索"
                font.pixelSize: 11
                color: Theme.textTertiary
            }

            Repeater {
                model: search.history
                delegate: Rectangle {
                    required property string modelData
                    width: chipText.implicitWidth + 24
                    height: 28
                    radius: 14
                    color: chipMouse.containsMouse ? Theme.accentSoft : (Theme.dark ? "#252431" : "#F0EFF7")
                    Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                    FluText {
                        id: chipText
                        anchors.centerIn: parent
                        text: modelData
                        font.pixelSize: 12
                        color: Theme.textSecondary
                    }
                    MouseArea {
                        id: chipMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: control.applyKeyword(modelData)
                    }
                }
            }

            FluTextButton {
                text: "清空"
                onClicked: search.clearHistory()
            }
        }

        // ── 来源标签 ────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            visible: search.hasResults || search.loading

            Repeater {
                model: control.tabs
                delegate: Rectangle {
                    required property var modelData
                    height: 30
                    width: tabRow.implicitWidth + 24
                    radius: 15
                    color: search.currentSource === modelData.id
                        ? Theme.accent
                        : (tabMouse.containsMouse ? Theme.accentSoft : (Theme.dark ? "#252431" : "#F0EFF7"))
                    Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                    Row {
                        id: tabRow
                        anchors.centerIn: parent
                        spacing: 6
                        FluText {
                            text: modelData.name
                            font.pixelSize: 12
                            font.weight: search.currentSource === modelData.id ? Font.DemiBold : Font.Normal
                            color: search.currentSource === modelData.id ? Theme.accentText : Theme.textSecondary
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        FluText {
                            text: String(modelData.count)
                            font.pixelSize: 10
                            color: search.currentSource === modelData.id
                                ? Qt.rgba(1, 1, 1, 0.75) : Theme.textTertiary
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    MouseArea {
                        id: tabMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: search.setSource(modelData.id)
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }

        // ── 置顶卡片（歌手 / 歌单，对应网易云的「综合」置顶）────
        // 高度必须写死：嵌套 RowLayout 里放了 fillHeight 的子项时，
        // 只给 Layout.preferredHeight 会被 ColumnLayout 当成可拉伸项，
        // 把下面的结果列表挤成 0 高（要配一个 maximumHeight 才压得住）。
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 92 : 0
            Layout.maximumHeight: 92
            visible: control.showTops
            spacing: 12

            // 歌手
            Rectangle {
                objectName: "searchTopArtistCard"
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                radius: Theme.radius
                visible: control.hasArtistCard
                color: artistMouse.containsMouse ? Theme.cardHover : Theme.cardBg
                border.width: 1
                border.color: Theme.border
                Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 68
                        Layout.preferredHeight: 68
                        Layout.alignment: Qt.AlignVCenter
                        radius: 34
                        color: Theme.accentSoft
                        clip: true

                        Image {
                            anchors.fill: parent
                            source: control.hasArtistCard ? search.topArtist.cover : ""
                            visible: source !== ""
                            fillMode: Image.PreserveAspectCrop
                            sourceSize.width: 136
                            sourceSize.height: 136
                        }
                        FluIcon {
                            anchors.centerIn: parent
                            visible: !(control.hasArtistCard && search.topArtist.cover !== "")
                            iconSource: FluentIcons.Contact
                            iconSize: 26
                            iconColor: Theme.accent
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 3

                        FluText {
                            Layout.fillWidth: true
                            text: control.hasArtistCard ? "歌手：" + search.topArtist.name : ""
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                            elide: Text.ElideRight
                        }
                        FluText {
                            Layout.fillWidth: true
                            text: {
                                if (!control.hasArtistCard)
                                    return ""
                                var parts = []
                                if (search.topArtist.music_size > 0)
                                    parts.push("单曲 " + search.topArtist.music_size)
                                if (search.topArtist.fans_size > 0)
                                    parts.push("粉丝 " + ArtistNames.formatCount(search.topArtist.fans_size))
                                return parts.join("  ·  ")
                            }
                            font.pixelSize: 11
                            color: Theme.textTertiary
                            elide: Text.ElideRight
                        }
                    }
                }

                MouseArea {
                    id: artistMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: artist.openById(search.topArtist.id, search.topArtist.name)
                }
            }

            // 歌单
            Rectangle {
                objectName: "searchTopPlaylistCard"
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                radius: Theme.radius
                visible: control.hasPlaylistCard
                color: playlistMouse.containsMouse ? Theme.cardHover : Theme.cardBg
                border.width: 1
                border.color: Theme.border
                Behavior on color { ColorAnimation { duration: Theme.durationFast } }

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 12

                    CoverArt {
                        Layout.preferredWidth: 68
                        Layout.preferredHeight: 68
                        Layout.alignment: Qt.AlignVCenter
                        radiusSize: Theme.radiusSmall
                        source: control.hasPlaylistCard ? search.topPlaylist.cover : ""
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 3

                        FluText {
                            Layout.fillWidth: true
                            text: control.hasPlaylistCard ? "歌单：" + search.topPlaylist.name : ""
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                            elide: Text.ElideRight
                        }
                        FluText {
                            Layout.fillWidth: true
                            text: {
                                if (!control.hasPlaylistCard)
                                    return ""
                                var parts = []
                                if (search.topPlaylist.creator !== "")
                                    parts.push(search.topPlaylist.creator)
                                if (search.topPlaylist.track_count > 0)
                                    parts.push(search.topPlaylist.track_count + " 首")
                                return parts.join("  ·  ")
                            }
                            font.pixelSize: 11
                            color: Theme.textTertiary
                            elide: Text.ElideRight
                        }
                    }
                }

                MouseArea {
                    id: playlistMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: discover.openPlaylist(search.topPlaylist.id, search.topPlaylist.name)
                }
            }

            Item { Layout.fillWidth: true }
        }

        // ── 结果 ────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.cardBg
            border.width: 1
            border.color: Theme.border
            clip: true

            TrackListView {
                id: resultList
                anchors.fill: parent
                anchors.margins: 6
                model: search.model
                busy: search.loading
                emptyIcon: FluentIcons.Search
                emptyTitle: search.keyword === "" ? "搜索你喜欢的音乐" : ("没有找到「" + search.keyword + "」")
                emptyDescription: search.keyword === ""
                    ? "支持同时搜索 5 个音源，播放失败时会自动跨源兜底"
                    : "换个关键词，或在其它音源标签页中查看"

                onTrackActivated: function (index) {
                    player.playTrackInList(search.model.allItems(), index)
                }
                onRequestPlayNow: function (track) { player.playTrack(track) }
                onRequestPlayNext: function (track) { player.playNextTrack(track) }
                onRequestAppend: function (track) { player.appendToQueue(track) }
                onRequestFavorite: function (track) { library.toggleFavorite(track) }
            }
        }

        // ── 分页 ────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 32 : 0
            visible: search.hasResults
            spacing: 8

            FluText {
                text: "第 " + search.page + " 页 · 共 " + search.resultCount + " 条"
                font.pixelSize: 11
                color: Theme.textTertiary
                Layout.alignment: Qt.AlignVCenter
            }

            Item { Layout.fillWidth: true }

            FluButton {
                text: "上一页"
                disabled: search.page <= 1 || search.loading
                onClicked: search.prevPage()
            }
            FluButton {
                text: "下一页"
                disabled: !search.hasMore || search.loading
                onClicked: search.nextPage()
            }
        }
    }

    /*!
        联想下拉：**挂在搜索框自己身上**（``parent: searchBox``），用锚点贴着它下沿

        不用 ``y: searchBox.mapToItem(control, 0, searchBox.height).y + 6`` 这种手算
        坐标：``mapToItem()`` 只是普通函数调用，在绑定里**建立不了依赖** —— 页面进场
        动画途中算出来的那一次偏移会被一直用下去，于是下拉盖住搜索框下半截（实测就是
        这么翻车的）。挂成子项之后，搜索框被布局挪到哪儿、下沿在哪儿，下拉就跟到哪儿。

        数据来自 ``search.suggestions``，服务端过滤，所以不用 FluentUI 自带的
        ``FluAutoSuggestBox`` —— 那个是按 ``title`` 在本地做子串过滤的，
        也带不了上下键选择。
    */
    Rectangle {
        id: suggestPanel
        objectName: "searchSuggestPanel"
        parent: searchBox
        anchors.top: parent.bottom
        anchors.topMargin: 6
        anchors.left: parent.left
        width: parent.width
        z: 50
        visible: control.suggestVisible
        height: Math.min(suggestList.contentHeight + 8, 300)
        radius: Theme.radius
        color: Theme.dark ? "#232230" : "#FFFFFF"
        border.width: 1
        border.color: Theme.border
        clip: true

        ListView {
            id: suggestList
            objectName: "searchSuggestList"
            anchors.fill: parent
            anchors.margins: 4
            model: control.suggestItems
            boundsBehavior: Flickable.StopAtBounds
            clip: true
            ScrollBar.vertical: FluScrollBar { }

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: suggestList.width
                height: 32
                radius: Theme.radiusSmall
                color: index === control.suggestIndex ? Theme.accentSoft : "transparent"

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 10
                    spacing: 8

                    FluIcon {
                        Layout.alignment: Qt.AlignVCenter
                        // 本地历史命中给时钟，接口联想词给放大镜
                        iconSource: String(modelData.from) === "history"
                            ? FluentIcons.History : FluentIcons.Search
                        iconSize: 12
                        iconColor: index === control.suggestIndex
                            ? Theme.accent : Theme.textTertiary
                    }
                    FluText {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        text: String(modelData.keyword)
                        font.pixelSize: 12
                        color: index === control.suggestIndex ? Theme.accent : Theme.textPrimary
                        elide: Text.ElideRight
                    }
                }

                MouseArea {
                    objectName: "searchSuggestItem"
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: control.suggestIndex = index
                    onClicked: control.applyKeyword(String(modelData.keyword))
                }
            }
        }
    }
}
