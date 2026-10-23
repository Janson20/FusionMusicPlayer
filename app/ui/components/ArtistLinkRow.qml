import QtQuick
import QtQuick.Layouts
import FluentUI
import ".."
import "../ArtistNames.js" as ArtistNames

/*!
    歌手行：逐个可点的歌手名 + 折叠。

    四个地方结构完全一样（列表行、播放栏、展开播放页、专辑页）：分隔符独立成项、
    超出 limit 位折叠成「等 N 人」、整行宽度夹在父项之内逐项省略 ——
    只是字号、颜色、上限宽度不同。原先各写五十来行，改一处忘三处。

    entries=true 时 source 是 [{id, name}]（专辑页的歌手实体，
    点进去要带 id）；否则是「A、B」这样的字符串。

    menuEnabled=false 表示「等 N 人」不做交互 —— 列表行把完整名单放在右键
    菜单里，行内再弹一个菜单会和右键菜单打架。
*/
Item {
    id: control

    //: 歌手来源：字符串（默认）或 [{id, name}]（entries=true 时）
    property var source: ""
    property bool entries: false
    //: 最多铺开几位（ArtistNames.DEFAULT_LIMIT = 3）
    property int limit: ArtistNames.DEFAULT_LIMIT

    property int pixelSize: 11
    property color normalColor: Theme.textTertiary
    property color hoverColor: Theme.accent

    //: 名字之间是否拉伸占满剩余宽度（列表行要，播放栏不要）
    property bool stretchLinks: false
    property int linkMinWidth: 28
    property int linkMaxWidth: 190
    property int moreMaxWidth: 190
    //: 行在自身宽度内怎么对齐（Text.AlignLeft / Text.AlignHCenter）
    property int horizontalAlign: Text.AlignLeft

    //: 「等 N 人」是否弹出完整名单
    property bool menuEnabled: true
    //: objectName 前缀：生成 <prefix>Link / <prefix>Sep / <prefix>More
    property string objectPrefix: "artistLink"
    //: 折叠菜单的 objectName（冒烟测试按名字读它的 names）
    property string menuObjectName: ""

    //: 点了某位歌手（entries=true 时 id 有值）
    signal artistActivated(string id, string name)
    //: 从完整名单里选了一位
    signal artistChosen(string name)

    readonly property var parts: control.entries
        ? ArtistNames.linkPartsOf(control.source || [], control.limit)
        : ArtistNames.linkParts(control.source === undefined ? "" : control.source, control.limit)

    readonly property var menuNames: {
        var items = (control.source === undefined || control.source === null) ? [] : control.source
        if (!control.entries)
            return ArtistNames.split(items)
        var out = []
        for (var i = 0; i < items.length; i++)
            out.push(String(items[i].name || ""))
        return out
    }

    implicitWidth: row.implicitWidth
    implicitHeight: row.implicitHeight
    visible: control.parts.length > 0

    RowLayout {
        id: row
        // 宽度夹在自身之内：放得下自然排，放不下逐项省略 —— 绝不让整行溢出
        width: Math.min(implicitWidth, control.width)
        x: control.horizontalAlign === Text.AlignHCenter
            ? Math.max(0, Math.round((control.width - width) / 2)) : 0
        spacing: 0

        Repeater {
            model: control.parts

            delegate: FluText {
                required property var modelData

                // 分隔符单独成项：不参与悬停高亮、不吃点击（否则「 / 」会被一起划上）
                objectName: modelData.more
                    ? control.objectPrefix + "More"
                    : (modelData.separator ? control.objectPrefix + "Sep"
                                           : control.objectPrefix + "Link")
                Layout.alignment: Qt.AlignVCenter
                Layout.fillWidth: control.stretchLinks && !modelData.separator
                Layout.minimumWidth: modelData.separator ? 0 : control.linkMinWidth
                Layout.maximumWidth: modelData.separator
                    ? Number.POSITIVE_INFINITY
                    : (modelData.more ? control.moreMaxWidth : control.linkMaxWidth)
                text: modelData.text
                font.pixelSize: control.pixelSize
                font.underline: !modelData.separator && !modelData.more && linkMouse.containsMouse
                color: (!modelData.separator && linkMouse.containsMouse)
                       ? control.hoverColor : control.normalColor
                elide: Text.ElideRight

                MouseArea {
                    id: linkMouse
                    anchors.fill: parent
                    enabled: !modelData.separator && (!modelData.more || control.menuEnabled)
                    hoverEnabled: !modelData.more
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        if (modelData.more) {
                            menu.popup()
                        } else if (control.entries) {
                            var node = modelData.item
                            control.artistActivated(node && node.id ? String(node.id) : "",
                                                    modelData.name)
                        } else {
                            control.artistActivated("", modelData.name)
                        }
                    }
                }
            }
        }
    }

    ArtistMenu {
        id: menu
        objectName: control.menuObjectName
        names: control.menuNames
        onArtistChosen: function (name) { control.artistChosen(name) }
    }
}
