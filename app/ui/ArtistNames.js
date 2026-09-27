.pragma library

/*!
    歌手名的拆分与展示。

    各音源都把自己的歌手列表拼成「、」分隔的字符串：酷我 / 酷狗 / 网易云 / QQ /
    咪咕原始数据里的 `&` `;` `/` 已经被 ``sources/utils.py:format_singer`` 换掉了，
    本地文件扫描时也走同一个归一化（``core/models.py:normalize_singers``）——
    所以这里默认只需要拆「、」，其余分隔符只是兜底。

    裸的 `/` 不拆：AC/DC 这种名字会被劈成两半。（归一化那一层是另一回事，
    它按音源的老规矩来，这里再拆一遍只会雪上加霜。）
*/

var SEPARATORS = /[、,，;；]|\s+\/\s+|\s+&\s+/

/*! 多个歌手之间的展示分隔符。 */
var SEPARATOR_TEXT = " / "

/*! 界面上最多直接铺开几位歌手；超出的部分折叠成「等 N 人」。
 *
 * 	为什么必须有这个上限：一首歌挂十几个歌手不算罕见（周年纪念集、企划曲），
 * 	而歌手行是按「名字 + 分隔符」逐个排的 -- 放不下时 QML 的 RowLayout **不会换行**，
 * 	它会把这行撑爆、横着盖到旁边的封面 / 歌词 / 时长上去（真机上见过一整行
 * 	从窗口最左铺到最右）。折叠之后无论多少个歌手都只占固定宽度。
 */
var DEFAULT_LIMIT = 3

/*! 把「A、B」拆成 ["A", "B"]（去重、去空）。 */
function split(text) {
    var raw = (text === undefined || text === null) ? "" : String(text)
    if (raw === "")
        return []
    var parts = raw.split(SEPARATORS)
    var out = []
    for (var i = 0; i < parts.length; i++) {
        var name = parts[i].trim()
        if (name !== "" && out.indexOf(name) < 0)
            out.push(name)
    }
    return out.length > 0 ? out : [raw]
}

/*! 折叠后的后缀文案：``等 16 人``。 */
function moreText(count) {
    return "等 " + count + " 人"
}

/*! 在若干条目之间插入**独立**的分隔片段。

    分隔符不能塞进歌手名里（`text: (index > 0 ? " / " : "") + name` 那种写法）：
    悬停时下划线会把「 / 」一起划上、颜色一起变成强调色，点击区域也把它算进去 ——
    看起来就像名字的一部分。
*/
function _interleave(items) {
    var out = []
    for (var i = 0; i < items.length; i++) {
        if (i > 0)
            out.push({ separator: true, name: "", item: null, text: SEPARATOR_TEXT })
        out.push({ separator: false, name: items[i].name, item: items[i], text: items[i].name })
    }
    return out
}

/*! 歌手名列表 → 渲染片段，超过 ``limit`` 位时末尾追加一个「等 N 人」片段。
 *
 *  ``limit <= 0`` 表示不折叠。折叠出来的片段带 ``more === true``，
 *  界面据此把它渲染成「查看全部」入口，而不是跳进某位歌手的主页。
 */
function _partsOf(names, limit) {
    var cap = (limit === undefined || limit === null) ? DEFAULT_LIMIT : Number(limit)
    var shown = names
    var hidden = 0
    if (cap > 0 && names.length > cap) {
        hidden = names.length - cap
        shown = names.slice(0, cap)
    }
    var out = _interleave(shown)
    if (hidden > 0) {
        out.push({ separator: true, name: "", item: null, text: SEPARATOR_TEXT })
        out.push({
            separator: false, more: true, name: "", item: null,
            hidden: hidden, total: names.length, text: moreText(names.length)
        })
    }
    return out
}

/*! 歌手字符串 → 渲染片段：``[{separator, name, item, text, more?}, …]``。

    界面按 ``separator`` 决定这一项能不能点、要不要跟着悬停高亮，
    按 ``more`` 决定它是「进入某位歌手」还是「展开完整列表」。
*/
function linkParts(text, limit) {
    var names = split(text)
    var items = []
    for (var i = 0; i < names.length; i++)
        items.push({ name: names[i] })
    return _partsOf(items, limit)
}

/*! 同上，但入参已经是拆好的 ``[{id, name}, …]``（专辑页的歌手列表）。 */
function linkPartsOf(items, limit) {
    return _partsOf(items || [], limit)
}

/*! 取第一位歌手（播放栏这类只放得下一个名字的地方用）。 */
function first(text) {
    var names = split(text)
    return names.length > 0 ? names[0] : ""
}

/*! 粉丝数这类大数字的紧凑写法：40894 -> 4.1 万。 */
function formatCount(value) {
    var n = Number(value) || 0
    if (n >= 100000000)
        return (n / 100000000).toFixed(1) + " 亿"
    if (n >= 10000)
        return (n / 10000).toFixed(1) + " 万"
    return String(n)
}
