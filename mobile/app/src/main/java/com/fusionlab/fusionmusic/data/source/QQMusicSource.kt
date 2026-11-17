package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.asIntOrNull
import com.fusionlab.fusionmusic.data.net.asLongOrNull
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.parseJsonObject
import com.fusionlab.fusionmusic.data.net.string
import com.fusionlab.fusionmusic.data.net.*
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import java.io.ByteArrayOutputStream
import java.util.zip.Inflater
import kotlin.random.Random

class QQMusicSource(
    timeoutSeconds: Int,
    proxy: String,
    log: AppLog?
) : BaseMusicSource("tx", "QQ音乐", timeoutSeconds, proxy, log) {
    override fun search(keyword: String, page: Int, limit: Int): List<MusicInfo> {
        val text = http.getText(
            TX_CLASSIC_SEARCH_URL,
            mapOf(
                "p" to page.toString(),
                "n" to limit.toString(),
                "w" to keyword,
                "format" to "json",
                "inCharset" to "utf-8",
                "outCharset" to "utf-8"
            ),
            mapOf("Referer" to "https://y.qq.com/")
        ) ?: return emptyList()
        val body = parseJsonObject(text) ?: return emptyList()
        val song = body.obj("data")?.obj("song") ?: return emptyList()
        setSearchTotal(song["totalnum"]?.jsonPrimitive?.content)
        return parseSearchResult(song.array("list") ?: return emptyList())
    }

    override fun getMusicUrl(info: MusicInfo, quality: String): String? {
        val mediaMid = (info.typeDetail[quality]?.get("media_mid"))?.jsonPrimitive?.content
            ?.takeIf { it.isNotBlank() } ?: info.songmid
        val prefix = TX_FILE_PREFIX[quality] ?: "C400"
        val ext = when (prefix) {
            "F000" -> ".flac"
            "M500" -> ".mp3"
            else -> ".m4a"
        }
        val fileName = prefix + mediaMid + ext
        val guid = (Random.nextLong(1000000000L, 9999999999L)).toString()

        try {
            val form = mapOf(
                "g_tk" to "5381",
                "loginUin" to "0",
                "hostUin" to "0",
                "format" to "json",
                "inCharset" to "utf-8",
                "outCharset" to "utf-8",
                "notice" to "0",
                "platform" to "yqq.json",
                "needNewCode" to "0",
                "cid" to "205361747",
                "uin" to "0",
                "songmid" to mediaMid,
                "filename" to fileName,
                "guid" to guid,
                "songtype" to "0"
            )
            val bytes = http.postForm(
                TX_EXPRESS_URL,
                form,
                mapOf("Referer" to "https://y.qq.com/")
            ).use { it.body?.bytes() }
            if (bytes != null) {
                parseExpress(bytes, guid)?.let { return it }
            }
        } catch (_: Exception) {
            // try the signed route below
        }

        try {
            val comm = jsonObject(
                "ct" to JsonPrimitive("11"),
                "cv" to JsonPrimitive("14090508"),
                "v" to JsonPrimitive("14090508"),
                "tmeAppID" to JsonPrimitive("qqmusic"),
                "uid" to JsonPrimitive("0"),
                "sid" to JsonPrimitive("0"),
                "nettype" to JsonPrimitive("1020")
            )
            val req = jsonObject(
                "module" to JsonPrimitive("music.vkey.GetVkey"),
                "method" to JsonPrimitive("CgiGetVkey"),
                "param" to jsonObject(
                    "guid" to JsonPrimitive(guid),
                    "songmid" to JsonPrimitive("[" + '"' + mediaMid + '"' + "]"),
                    "songtype" to JsonPrimitive("[0]"),
                    "uin" to JsonPrimitive("0"),
                    "loginflag" to JsonPrimitive(1),
                    "platform" to JsonPrimitive("23")
                )
            )
            val payload = jsonObject("comm" to comm, "req" to req)
            val raw = payload.toString()
            val sign = Crypto.txZzcSign(raw)
            val body = "zzc_sign=" + sign + "&" + raw
            val text = http.postBytes(TX_SIGN_URL, body.toByteArray(Charsets.UTF_8)).use { response ->
                if (!response.isSuccessful) null else response.body?.string()
            } ?: return null
            val midurlinfo = parseJsonObject(text)?.obj("req")?.obj("data")?.array("midurlinfo")
            val purl = (midurlinfo?.firstOrNull() as? JsonObject)?.string("purl") ?: return null
            if (purl.isNotBlank()) return "http://ws.stream.qqmusic.qq.com/" + purl
        } catch (_: Exception) {
            // no address on this route
        }
        return null
    }

    override fun getLyric(info: MusicInfo): String? {
        try {
            val text = http.getText(
                TX_LYRIC_URL,
                mapOf("songmid" to info.songmid, "format" to "json", "nobase64" to "1"),
                mapOf("Referer" to "https://y.qq.com/")
            )
            val body = parseJsonObject(text)
            if (body?.int("retcode") == 0) {
                val lyric = body.string("lyric")
                if (lyric.isNotBlank()) return lyric
            }
        } catch (_: Exception) {
            // try signed route
        }
        return null
    }

    override fun getPicUrl(info: MusicInfo): String? {
        return "https://y.qq.com/music/photo_new/T002R300x300M000" + info.songmid + ".jpg"
    }

    override fun getDownloadHeaders(): Map<String, String> = mapOf("Referer" to "https://y.qq.com/")

    private fun parseSearchResult(items: kotlinx.serialization.json.JsonArray): List<MusicInfo> {
        val results = mutableListOf<MusicInfo>()
        for (element in items) {
            val item = element as? JsonObject ?: continue
            try {
                val songmid = item.string("songmid")
                if (songmid.isBlank()) continue
                val mediaMid = item.string("media_mid").ifBlank { songmid }
                val singers = item.array("singer")?.mapNotNull { singer ->
                    (singer as? JsonObject)?.string("name")?.let { Crypto.formatSinger(Crypto.decodeName(it)) }
                } ?: emptyList()
                val types = parseTypes(item, mediaMid)
                results.add(
                    MusicInfo(
                        name = Crypto.decodeName(item.string("songname").ifBlank { item.string("name") }),
                        singer = singers.joinToString("、"),
                        source = sourceId,
                        songmid = songmid,
                        albumName = Crypto.decodeName(item.string("albumname")),
                        albumId = item.string("albummid"),
                        interval = item.int("interval"),
                        types = types.first,
                        typeDetail = types.second
                    )
                )
            } catch (_: Exception) {
                // skip malformed item
            }
        }
        return results
    }

    private fun parseTypes(item: JsonObject, mediaMid: String): Pair<List<JsonObject>, Map<String, JsonObject>> {
        val qualityMap = listOf(
            "size128" to "128k",
            "size320" to "320k",
            "sizeflac" to "flac",
            "sizehires" to "flac24bit"
        )
        val types = mutableListOf<JsonObject>()
        val details = LinkedHashMap<String, JsonObject>()
        for ((sizeKey, quality) in qualityMap) {
            val size = item[sizeKey]?.asLongOrNull() ?: 0L
            if (size > 0) {
                types.add(jsonObject("type" to JsonPrimitive(quality), "size" to JsonPrimitive(formatSize(size))))
                details[quality] = jsonObject(
                    "size" to JsonPrimitive(formatSize(size)),
                    "media_mid" to JsonPrimitive(mediaMid)
                )
            }
        }
        return Pair(types, details)
    }

    private fun parseExpress(raw: ByteArray, guid: String): String? {
        val body = if (raw.size >= 5 && raw.sliceArray(0 until 5).all { it.toInt() == 0 }) raw.copyOfRange(5, raw.size) else raw
        val decoded = try {
            inflate(body)
        } catch (_: Exception) {
            body
        }
        val payload = parseJsonObject(decoded.toString(Charsets.UTF_8)) ?: return null
        val items = payload.obj("data")?.array("items") ?: return null
        val item = items.firstOrNull() as? JsonObject ?: return null
        val vkey = item.string("vkey")
        val fname = item.string("filename")
        if (vkey.isBlank() || fname.isBlank() || vkey.lowercase().contains("error")) return null
        return "http://ws.stream.qqmusic.qq.com/" + fname + "?vkey=" + vkey + "&guid=" + guid + "&uin=0&fromtag=66"
    }

    private fun inflate(data: ByteArray): ByteArray {
        val inflater = Inflater()
        inflater.setInput(data)
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        try {
            while (!inflater.finished()) {
                val count = inflater.inflate(buffer)
                if (count == 0) {
                    if (inflater.needsInput() || inflater.needsDictionary()) break
                    continue
                }
                output.write(buffer, 0, count)
            }
        } finally {
            inflater.end()
        }
        return output.toByteArray()
    }

    companion object {
        private const val TX_SIGN_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
        private const val TX_CLASSIC_SEARCH_URL = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
        private const val TX_EXPRESS_URL = "https://c.y.qq.com/base/fcgi-bin/fcg_music_express_mobile3.fcg"
        private const val TX_LYRIC_URL = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"
        private val TX_FILE_PREFIX = mapOf("flac24bit" to "F000", "flac" to "F000", "320k" to "M500", "128k" to "C400")
    }
}
