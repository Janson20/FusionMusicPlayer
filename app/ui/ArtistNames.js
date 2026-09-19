.pragma library

/*!
    歌手名的拆分与展示。

    各音源都把自己的歌手列表拼成「、」分隔的字符串 —— 酷我 / 酷狗原始数据里的
    `&` `;` `/` 已经被 ``sources/utils.py:format_singer`` 换成「、」了 ——
    所以默认只需要拆「、」，其余分隔符只是兜底。

    裸的 `/` 不拆：AC/DC 这种名字会被劈成两半。
*/

var SEPARATORS = /[、,，;；]|\s+\/\s+|\s+&\s+/

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
