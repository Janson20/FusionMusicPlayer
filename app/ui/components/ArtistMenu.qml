import QtQuick
import QtQuick.Controls
import FluentUI
import ".."

/*!
    歌手折叠后的「完整列表」菜单。

    歌手行只铺开前几位（见 ``ArtistNames.js`` 的 ``DEFAULT_LIMIT``）——
    不折叠的话十几个歌手会把整行撑爆、横着盖到封面 / 歌词上去。
    被折叠掉的那些从这里进去：每一项都能点进对应的歌手主页。
*/
FluMenu {
    id: control

    /*! 完整的歌手名列表（已拆分、去重）。 */
    property var names: []

    signal artistChosen(string name)

    width: 200

    Repeater {
        model: control.names
        delegate: FluMenuItem {
            required property string modelData
            text: modelData
            onClicked: control.artistChosen(modelData)
        }
    }
}
