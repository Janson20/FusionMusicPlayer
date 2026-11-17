package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.asLongOrNull
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.parseJsonObject
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import java.util.Locale

class MiguMusicSource(
    timeoutSeconds: Int,
    proxy: String,
    log: AppLog?
) : BaseMusicSource("mg", "咪咕音乐", timeoutSeconds, proxy, log) {
    override val searchLimit: Int = 20

    override fun search(keyword: String, page: Int, limit: Int): List<MusicInfo> {
        val timestamp = System.currentTimeMillis()
        val sign = Crypto.mgCreateSign(timestamp, keyword)
        val params = mapOf(
            "ua" to "Android_migu",
            "version" to "5.0.1",
            "text" to keyword,
            "pageNo" to page.toString(),
            "pageSize" to limit.toString(),
            "searchSwitch" to "{\"song\":1,\"album\":0,\"singer\":0,\"tagSong\":0,\"mvSong\":0,\"songlist\":0,\"bestShow\":1}",
            "isCopyright" to "1",
            "isCorrect" to "1",
            "sort" to "0"
        )
        val headers = mapOf(
            "sign" to sign,
            "timestamp" to timestamp.toString(),
            "appId" to "yyapp2",
            "mode" to "android",
            "ua" to "Android_migu",
            "version" to "6.9.4",
            "osVersion" to "android 7.0",
            "deviceId" to MG_DEVICE_ID
        )
        val text = http.getText(MG_SEARCH_URL, params, headers) ?: return emptyList()
        val body = parseJsonObject(text) ?: return emptyList()
        val data = body.obj("songResultData") ?: return emptyList()
        val list = data.array("resultList") ?: data.array("result") ?: return emptyList()
        if (list.isEmpty()) return emptyList()
        setSearchTotal(data["totalCount"]?.jsonPrimitive?.content)
        return parseSearchResult(list)
    }

    override fun getMusicUrl(info: MusicInfo, quality: String): String? {
        val qInfo = info.typeDetail[quality]
            ?: info.typeDetail.entries.firstOrNull()?.value
            ?: return null
        val timestamp = System.currentTimeMillis()
        val params = mapOf(
            "contentId" to info.songmid,
            "copyrightId" to info.songmid,
            "netType" to "01",
            "toneFlag" to (qInfo.string("formatType").ifBlank { "PQ" }),
            "resourceType" to (qInfo.string("resourceType").ifBlank { "2" }),
            "channel" to "0",
            "ua" to "Android_migu",
            "version" to "5.0.1",
            "appId" to "yyapp2",
            "deviceId" to MG_DEVICE_ID
        )
        val headers = mapOf(
            "sign" to Crypto.mgCreateSign(timestamp, ""),
            "timestamp" to timestamp.toString(),
            "mode" to "android",
            "osVersion" to "android 7.0"
        )
        val text = http.getText(MG_LISTEN_URL, params, headers) ?: return null
        val body = parseJsonObject(text) ?: return null
        if (body.string("code") != "000000") return null
        val listens = body.array("songListens") ?: return null
        val first = listens.firstOrNull() as? JsonObject ?: return null
        return first.string("url").ifBlank { null }
    }

    override fun getLyric(info: MusicInfo): String? {
        val url = info.lrc
        if (url.isNullOrBlank()) return null
        val text = http.getText(url) ?: return null
        val lines = mutableListOf<String>()
        var seconds = 0L
        for (raw in text.split("\n")) {
            val line = raw.trim()
            if (line.isEmpty() || line.startsWith("@")) continue
            val minutes = seconds / 60
            val secs = seconds % 60
            lines.add(String.format(Locale.US, "[%02d:%05.2f]%s", minutes, secs.toDouble(), line))
            seconds += 4
        }
        return if (lines.isEmpty()) null else lines.joinToString("\n")
    }

    override fun getPicUrl(info: MusicInfo): String? {
        if (info.img?.isNotBlank() == true) return info.img
        val text = http.getText(
            MG_RESOURCE_URL,
            mapOf(
                "ua" to "Android_migu",
                "version" to "5.0.1",
                "needImage" to "1",
                "copyrightId" to info.songmid
            )
        ) ?: return null
        val body = parseJsonObject(text) ?: return null
        val images = body.obj("data")?.array("albumImgs") ?: return null
        val first = images.firstOrNull() as? JsonObject ?: return null
        return first.string("img").ifBlank { null }
    }

    private fun parseSearchResult(rawList: JsonArray): List<MusicInfo> {
        val results = mutableListOf<MusicInfo>()
        val seen = mutableSetOf<String>()
        for (element in rawList) {
            var item: JsonObject? = element as? JsonObject
            if (element is JsonArray) item = element.firstOrNull() as? JsonObject
            if (item == null) continue
            try {
                val songId = sequenceOf("contentId", "id", "songId", "copyrightId")
                    .map { item.string(it) }
                    .firstOrNull { it.isNotBlank() }
                    ?: continue
                if (songId in seen) continue
                seen.add(songId)
                val types = parseTypes(item)
                val duration = parseDuration(item)
                val singers = item["singers"] ?: item["singer"]
                val singer = when {
                    singers is JsonArray -> singers.mapNotNull { singerElement ->
                        (singerElement as? JsonObject)?.string("name")?.let { Crypto.formatSinger(Crypto.decodeName(it)) }
                    }.joinToString("、")
                    singers is JsonPrimitive -> Crypto.formatSinger(Crypto.decodeName(singers.content))
                    else -> ""
                }
                val albums = item.array("albums")
                val albumName = if (albums != null && albums.isNotEmpty()) {
                    (albums.firstOrNull() as? JsonObject)?.string("name") ?: ""
                } else {
                    item.string("albumName").ifBlank { item.string("album") }
                }
                val images = item.array("albumImgs") ?: item.array("imgItems")
                val image = (images?.firstOrNull() as? JsonObject)?.string("img") ?: ""
                val playCount = sequenceOf("listenCount", "playCount", "listen_cnt")
                    .map { item[it]?.asLongOrNull() ?: 0L }
                    .firstOrNull { it > 0 } ?: 0L
                results.add(
                    MusicInfo(
                        name = Crypto.decodeName(item.string("name").ifBlank { item.string("songName") }),
                        singer = singer,
                        source = sourceId,
                        songmid = songId,
                        albumName = Crypto.decodeName(albumName),
                        albumId = item.string("albumId"),
                        interval = duration,
                        img = image.ifBlank { null },
                        types = types.first,
                        typeDetail = types.second,
                        playCount = playCount,
                        lrc = item.string("lyricUrl").ifBlank { null }
                    )
                )
            } catch (_: Exception) {
                // skip malformed item
            }
        }
        return results
    }

    private fun parseTypes(item: JsonObject): Pair<List<JsonObject>, Map<String, JsonObject>> {
        val formats = item.array("newRateFormats") ?: item.array("rateFormats") ?: return Pair(emptyList(), emptyMap())
        val types = mutableListOf<JsonObject>()
        val details = LinkedHashMap<String, JsonObject>()
        for (element in formats) {
            val format = element as? JsonObject ?: continue
            val formatType = format.string("formatType")
            val quality = when (formatType) {
                "PQ" -> "128k"
                "HQ" -> "320k"
                "SQ" -> "flac"
                "ZQ" -> "flac24bit"
                else -> continue
            }
            types.add(jsonObject("type" to JsonPrimitive(quality)))
            details[quality] = jsonObject(
                "formatType" to JsonPrimitive(formatType),
                "resourceType" to JsonPrimitive(format.string("resourceType"))
            )
        }
        return Pair(types, details)
    }

    private fun parseDuration(item: JsonObject): Int {
        val raw = item["duration"] ?: item["length"] ?: item["auditionsLength"] ?: return 0
        return raw.asLongOrNull()?.toInt() ?: 0
    }

    companion object {
        private const val MG_SEARCH_URL = "https://app.c.nf.migu.cn/MIGUM2.0/v1.0/content/search_all.do"
        private const val MG_LISTEN_URL = "https://app.c.nf.migu.cn/MIGUM3.0/v1.0/content/sub/listen.do"
        private const val MG_RESOURCE_URL = "https://app.c.nf.migu.cn/MIGUM2.0/v1.0/content/resourceinfo.do"
        private const val MG_DEVICE_ID = "963B7AA0D21511ED807EE5846EC87D20"
    }
}
