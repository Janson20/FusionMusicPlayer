package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.asArrayOrNull
import com.fusionlab.fusionmusic.data.net.asObjectOrNull
import com.fusionlab.fusionmusic.data.net.asStringOrNull
import com.fusionlab.fusionmusic.data.net.int
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.listObjects
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.parseJson
import com.fusionlab.fusionmusic.data.net.parseJsonObject
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import java.util.Locale

class KuwoMusicSource(
    timeoutSeconds: Int,
    proxy: String,
    log: AppLog?
) : BaseMusicSource("kw", "酷我音乐", timeoutSeconds, proxy, log) {
    override fun search(keyword: String, page: Int, limit: Int): List<MusicInfo> {
        val text = http.getText(
            KW_SEARCH_URL,
            mapOf(
                "client" to "kt",
                "all" to keyword,
                "pn" to (page - 1).toString(),
                "rn" to limit.toString(),
                "uid" to "794762570",
                "ver" to "kwplayer_ar_9.2.2.1",
                "vipver" to "1",
                "show_copyright_off" to "1",
                "newver" to "1",
                "ft" to "music",
                "cluster" to "0",
                "strategy" to "2012",
                "encoding" to "utf8",
                "rformat" to "json",
                "vermerge" to "1",
                "mobi" to "1",
                "issubtitle" to "1"
            )
        ) ?: return emptyList()
        val element = parseJson(text) ?: return emptyList()
        val items: List<JsonObject>
        if (element is JsonObject) {
            setSearchTotal(element["TOTAL"]?.jsonPrimitive?.content)
            items = element.listObjects("abslist")
        } else {
            val array = element.asArrayOrNull() ?: return emptyList()
            setSearchTotal(0)
            items = array.mapNotNull { it as? JsonObject }
        }
        return parseSearchResult(items)
    }

    override fun getMusicUrl(info: MusicInfo, quality: String): String? {
        val br = BR_MAP[quality] ?: "128kmp3"
        try {
            val text = http.getText(
                KW_ANTISERVER_URL,
                mapOf(
                    "type" to "convert_url3",
                    "rid" to "MUSIC_" + info.songmid,
                    "format" to "mp3",
                    "response" to "url",
                    "br" to br
                ),
                mapOf("Referer" to "https://www.kuwo.cn/")
            )
            val body = parseJsonObject(text)
            val url = body?.string("url")
            if (!url.isNullOrBlank()) return url
        } catch (_: Exception) {
            // try old route
        }
        try {
            val text = http.getText(
                KW_MUSIC_URL,
                mapOf(
                    "format" to "mp3",
                    "rid" to "MUSIC_" + info.songmid,
                    "response" to "url",
                    "type" to "convert_url3",
                    "br" to br,
                    "from" to "web"
                ),
                mapOf("Referer" to "https://www.kuwo.cn/")
            )
            return parseJsonObject(text)?.string("url")?.ifBlank { null }
        } catch (_: Exception) {
            return null
        }
    }

    override fun getLyric(info: MusicInfo): String? {
        val text = http.getText(
            KW_LYRIC_URL,
            mapOf("musicId" to info.songmid),
            mapOf("Referer" to "http://m.kuwo.cn/")
        ) ?: return null
        val data = parseJsonObject(text)?.obj("data") ?: return null
        val list = data.array("lrclist") ?: return null
        if (list.isEmpty()) return null
        val lines = mutableListOf<String>()
        val songName = Crypto.decodeName(data.obj("songinfo")?.string("songName") ?: "")
        val artist = Crypto.decodeName(data.obj("songinfo")?.string("artist") ?: "")
        if (songName.isNotBlank()) lines.add("[ti:" + songName + "]")
        if (artist.isNotBlank()) lines.add("[ar:" + artist + "]")
        lines.add("[offset:0]")
        for (element in list) {
            val item = element as? JsonObject ?: continue
            val time = item["time"]?.jsonPrimitive?.content?.toDoubleOrNull() ?: 0.0
            val lyric = Crypto.decodeName(item.string("lineLyric"))
            val minutes = (time / 60).toInt()
            val seconds = time % 60
            lines.add(String.format(Locale.US, "[%02d:%05.2f]%s", minutes, seconds, lyric))
        }
        return lines.joinToString("\n")
    }

    override fun getPicUrl(info: MusicInfo): String? {
        val text = http.getText(
            KW_PIC_URL,
            mapOf("flag" to "6", "rid" to "MUSIC_" + info.songmid)
        )
        return text?.trim()?.ifBlank { null }
    }

    override fun getDownloadHeaders(): Map<String, String> = mapOf("Referer" to "http://www.kuwo.cn/")

    private fun parseSearchResult(items: List<JsonObject>): List<MusicInfo> {
        val results = mutableListOf<MusicInfo>()
        for (item in items) {
            try {
                val songId = item.string("MUSICRID").replace("MUSIC_", "")
                if (songId.isBlank()) continue
                val minfo = item.string("N_MINFO")
                if (minfo.isBlank()) continue
                val types = parseTypes(minfo)
                results.add(
                    MusicInfo(
                        name = Crypto.decodeName(item.string("SONGNAME")),
                        singer = Crypto.formatSinger(Crypto.decodeName(item.string("ARTIST"))),
                        source = sourceId,
                        songmid = songId,
                        albumName = Crypto.decodeName(item.string("ALBUM")),
                        albumId = Crypto.decodeName(item.string("ALBUMID")),
                        interval = item.int("DURATION").takeIf { it > 0 } ?: 0,
                        types = types.first,
                        typeDetail = types.second,
                        playCount = parsePlayCount(item).toLong()
                    )
                )
            } catch (_: Exception) {
                // skip malformed item
            }
        }
        return results
    }

    private fun parseTypes(nMinfo: String): Pair<List<JsonObject>, Map<String, JsonObject>> {
        val types = mutableListOf<JsonObject>()
        val details = LinkedHashMap<String, JsonObject>()
        for (match in MINFO_RE.findAll(nMinfo)) {
            val bitrate = match.groupValues[2]
            val size = match.groupValues[4]
            val quality = TYPE_MAP[bitrate] ?: continue
            types.add(jsonObject("type" to JsonPrimitive(quality), "size" to JsonPrimitive(size)))
            details[quality] = jsonObject("size" to JsonPrimitive(size))
        }
        types.reverse()
        return Pair(types, details)
    }

    private fun parsePlayCount(item: JsonObject): Int {
        val raw = item["PLAYCNT"] ?: item["playCnt"] ?: item["playCount"] ?: return 0
        return raw.asStringOrNull()?.toIntOrNull() ?: 0
    }

    companion object {
        private const val KW_SEARCH_URL = "https://search.kuwo.cn/r.s"
        private const val KW_LYRIC_URL = "https://m.kuwo.cn/newh5/singles/songinfoandlrc"
        private const val KW_MUSIC_URL = "https://www.kuwo.cn/url"
        private const val KW_ANTISERVER_URL = "http://antiserver.kuwo.cn/anti.s"
        private const val KW_PIC_URL = "https://player.kuwo.cn/webmusic/sj/dtflagdate"
        private val MINFO_RE = Regex("level:(\\w+),bitrate:(\\d+),format:(\\w+),size:([\\w.]+)")
        private val TYPE_MAP = mapOf("4000" to "flac24bit", "2000" to "flac", "320" to "320k", "128" to "128k")
        private val BR_MAP = mapOf(
            "flac24bit" to "4000kflac24bit",
            "flac" to "2000kflac",
            "320k" to "320kmp3",
            "128k" to "128kmp3"
        )
    }
}
