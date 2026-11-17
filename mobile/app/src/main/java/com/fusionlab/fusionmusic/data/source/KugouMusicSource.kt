package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.asLongOrNull
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.listObjects
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.parseJsonObject
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import java.util.Base64

class KugouMusicSource(
    timeoutSeconds: Int,
    proxy: String,
    log: AppLog?
) : BaseMusicSource("kg", "酷狗音乐", timeoutSeconds, proxy, log) {
    override fun search(keyword: String, page: Int, limit: Int): List<MusicInfo> {
        val text = http.getText(
            KG_SEARCH_URL,
            mapOf(
                "keyword" to keyword,
                "page" to page.toString(),
                "pagesize" to limit.toString(),
                "userid" to "0",
                "clientver" to "",
                "platform" to "WebFilter",
                "filter" to "2",
                "iscorrection" to "1",
                "privilege_filter" to "0",
                "area_code" to "1"
            )
        ) ?: return emptyList()
        val body = parseJsonObject(text) ?: return emptyList()
        val data = body.obj("data") ?: return emptyList()
        setSearchTotal(data["total"]?.jsonPrimitive?.content)
        return parseSearchResult(data.listObjects("lists"))
    }

    override fun getMusicUrl(info: MusicInfo, quality: String): String? {
        val hash = info.typeDetail[quality]?.string("hash")?.takeIf { it.isNotBlank() }
            ?: info.typeDetail.values.firstOrNull()?.string("hash")?.takeIf { it.isNotBlank() }
            ?: return null
        try {
            val text = http.getText(
                KG_PLAY_INFO_URL,
                mapOf("cmd" to "playInfo", "hash" to hash),
                mapOf("Referer" to "https://m.kugou.com/")
            )
            val data = parseJsonObject(text)
            val url = data?.string("url")
            if (!url.isNullOrBlank()) return url
            val backup = data?.get("backup_url")
            if (backup is JsonPrimitive) return backup.content.ifBlank { null }
            if (backup is kotlinx.serialization.json.JsonArray) {
                for (item in backup) {
                    val value = (item as? JsonPrimitive)?.content
                    if (!value.isNullOrBlank()) return value
                }
            }
        } catch (_: Exception) {
            // try tracker route
        }
        try {
            val keyText = http.getText(
                KG_TRACKER_URL,
                mapOf(
                    "cmd" to "4",
                    "hash" to hash,
                    "key" to info.songmid,
                    "pid" to "1",
                    "acceptMp3" to "1"
                ),
                mapOf("Referer" to "https://www.kugou.com/")
            )
            val key = parseJsonObject(keyText)?.obj("data")?.string("key") ?: return null
            if (key.isBlank()) return null
            val dataText = http.getText(
                KG_GET_DATA_URL,
                mapOf("r" to "play/getdata", "hash" to hash, "key" to key, "mid" to "135477665551482173"),
                mapOf("Referer" to "https://www.kugou.com/")
            )
            val data = parseJsonObject(dataText)?.obj("data") ?: return null
            return data.string("play_url").ifBlank { data.string("url") }.ifBlank { null }
        } catch (_: Exception) {
            return null
        }
    }

    override fun getLyric(info: MusicInfo): String? {
        val hash = info.typeDetail["128k"]?.string("hash")?.takeIf { it.isNotBlank() }
            ?: info.typeDetail.values.firstOrNull()?.string("hash")?.takeIf { it.isNotBlank() }
            ?: return null
        try {
            val searchText = http.getText(
                KG_LYRIC_URL,
                mapOf(
                    "keyword" to (info.name + " " + info.singer),
                    "hash" to hash,
                    "timelength" to (if (info.interval > 0) (info.interval * 1000).toString() else "0"),
                    "clientver" to ""
                )
            )
            val search = parseJsonObject(searchText) ?: return null
            val candidates = search.obj("data")?.array("lists")
                ?: search.array("candidates")
                ?: return null
            val first = candidates.firstOrNull() as? JsonObject ?: return null
            val lyricId = first.string("id")
            val accessKey = first.string("accesskey")
            if (lyricId.isBlank() || accessKey.isBlank()) return null
            val downloadText = http.getText(
                KG_LYRIC_DOWNLOAD,
                mapOf(
                    "id" to lyricId,
                    "accesskey" to accessKey,
                    "fmt" to "lrc",
                    "charset" to "utf8",
                    "ver" to "1",
                    "client" to "pc"
                )
            )
            val content = parseJsonObject(downloadText)?.string("content") ?: return null
            if (content.isBlank()) return null
            return try {
                String(Base64.getDecoder().decode(content), Charsets.UTF_8)
            } catch (_: Exception) {
                content
            }
        } catch (_: Exception) {
            return null
        }
    }

    override fun getPicUrl(info: MusicInfo): String? {
        if (info.img?.isNotBlank() == true) return info.img
        val hash = info.typeDetail["128k"]?.string("hash")?.takeIf { it.isNotBlank() }
            ?: info.typeDetail.values.firstOrNull()?.string("hash")?.takeIf { it.isNotBlank() }
            ?: return null
        try {
            val text = http.getText(KG_GET_DATA_URL, mapOf("r" to "play/getdata", "hash" to hash))
            val img = parseJsonObject(text)?.obj("data")?.string("img")
            if (!img.isNullOrBlank()) return img
        } catch (_: Exception) {
            // fall through
        }
        return "https://imge.kugou.com/stdmusic/120/" + hash + ".png"
    }

    override fun getDownloadHeaders(): Map<String, String> = mapOf("Referer" to "https://m.kugou.com/")

    private fun parseSearchResult(items: List<JsonObject>): List<MusicInfo> {
        val results = mutableListOf<MusicInfo>()
        val seen = mutableSetOf<String>()
        for (item in items) {
            try {
                val songId = item.string("Audioid")
                val hash = item.string("FileHash")
                val key = songId + "_" + hash
                if (key in seen) continue
                seen.add(key)
                val types = parseTypes(item)
                results.add(
                    MusicInfo(
                        name = Crypto.decodeName(item.string("SongName")),
                        singer = formatSingers(item.array("Singers")),
                        source = sourceId,
                        songmid = songId,
                        albumName = Crypto.decodeName(item.string("AlbumName")),
                        albumId = item.string("AlbumID"),
                        interval = item["Duration"]?.asLongOrNull()?.toInt() ?: 0,
                        types = types.first,
                        typeDetail = types.second,
                        playCount = item["TotalPlayCnt"]?.asLongOrNull() ?: 0L
                    )
                )
                val children = item.array("Grp") ?: continue
                for (childElement in children) {
                    val child = childElement as? JsonObject ?: continue
                    val childKey = child.string("Audioid") + "_" + child.string("FileHash")
                    if (childKey in seen) continue
                    seen.add(childKey)
                    val childTypes = parseTypes(child)
                    results.add(
                        MusicInfo(
                            name = Crypto.decodeName(child.string("SongName")),
                            singer = formatSingers(child.array("Singers")),
                            source = sourceId,
                            songmid = child.string("Audioid"),
                            albumName = Crypto.decodeName(child.string("AlbumName")),
                            albumId = child.string("AlbumID"),
                            interval = child["Duration"]?.asLongOrNull()?.toInt() ?: 0,
                            types = childTypes.first,
                            typeDetail = childTypes.second,
                            playCount = child["TotalPlayCnt"]?.asLongOrNull() ?: 0L
                        )
                    )
                }
            } catch (_: Exception) {
                // skip malformed item
            }
        }
        return results
    }

    private fun parseTypes(item: JsonObject): Pair<List<JsonObject>, Map<String, JsonObject>> {
        val types = mutableListOf<JsonObject>()
        val details = LinkedHashMap<String, JsonObject>()
        val qualityMap = listOf(
            Triple("FileSize", "FileHash", "128k"),
            Triple("HQFileSize", "HQFileHash", "320k"),
            Triple("SQFileSize", "SQFileHash", "flac"),
            Triple("ResFileSize", "ResFileHash", "flac24bit")
        )
        for ((sizeKey, hashKey, quality) in qualityMap) {
            val size = item[sizeKey]?.asLongOrNull() ?: 0L
            if (size > 0) {
                types.add(jsonObject("type" to JsonPrimitive(quality), "size" to JsonPrimitive(formatSize(size))))
                details[quality] = jsonObject(
                    "size" to JsonPrimitive(formatSize(size)),
                    "hash" to JsonPrimitive(item.string(hashKey))
                )
            }
        }
        return Pair(types, details)
    }

    private fun formatSingers(singers: kotlinx.serialization.json.JsonArray?): String {
        if (singers == null) return ""
        return singers.mapNotNull { singer ->
            (singer as? JsonObject)?.string("name")?.takeIf { it.isNotBlank() }?.let { Crypto.decodeName(it) }
        }.joinToString("、")
    }

    companion object {
        private const val KG_SEARCH_URL = "https://songsearch.kugou.com/song_search_v2"
        private const val KG_LYRIC_URL = "https://lyrics.kugou.com/search"
        private const val KG_LYRIC_DOWNLOAD = "https://lyrics.kugou.com/download"
        private const val KG_PLAY_INFO_URL = "https://m.kugou.com/app/i/getSongInfo.php"
        private const val KG_TRACKER_URL = "https://trackercdn.kugou.com/i/"
        private const val KG_GET_DATA_URL = "https://wwwapi.kugou.com/yy/index.php"
    }
}
