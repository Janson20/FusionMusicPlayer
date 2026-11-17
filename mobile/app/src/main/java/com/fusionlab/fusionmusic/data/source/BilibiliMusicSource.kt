package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.asLongOrNull
import com.fusionlab.fusionmusic.data.net.int
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.parseJsonObject
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

class BilibiliMusicSource(
    timeoutSeconds: Int,
    proxy: String,
    log: AppLog?
) : BaseMusicSource("bili", "哔哩哔哩", timeoutSeconds, proxy, log) {
    private var cookiesReady = false
    private var wbiKeys: Pair<String, String>? = null
    private var wbiExpireAt: Long = 0L
    private val cidCache = ConcurrentHashMap<String, Long>()

    override fun search(keyword: String, page: Int, limit: Int): List<MusicInfo> {
        ensureCookies()
        val keys = getWbiKeys() ?: return emptyList()
        val params = mapOf(
            "search_type" to "video",
            "keyword" to keyword,
            "page" to page.toString(),
            "page_size" to limit.toString(),
            "order" to "totalrank",
            "platform" to "pc",
            "web_location" to "1430654"
        )
        val signed = Crypto.biliWbiSign(params, keys.first, keys.second)
        val text = http.getText(
            BILI_SEARCH_API,
            signed,
            mapOf(
                "Origin" to "https://search.bilibili.com",
                "Referer" to "https://search.bilibili.com/video?keyword=" + java.net.URLEncoder.encode(keyword, "UTF-8")
            )
        ) ?: return emptyList()
        val body = parseJsonObject(text) ?: return emptyList()
        if (body.int("code") != 0) return emptyList()
        val data = body.obj("data") ?: return emptyList()
        if (data["v_voucher"] != null) {
            log?.w("Bilibili", "search triggered v_voucher risk control")
            return emptyList()
        }
        val numResults = data["numResults"]?.asLongOrNull() ?: 0L
        val numPages = data["numPages"]?.asLongOrNull() ?: 0L
        setSearchTotal(if (numResults > 0) numResults else numPages * limit)
        return parseSearchResult(data.array("result") ?: return emptyList())
    }

    override fun getMusicUrl(info: MusicInfo, quality: String): String? {
        ensureCookies()
        val bvid = info.songmid
        if (bvid.isBlank()) return null
        val cid = getCid(bvid) ?: return null
        val text = http.getText(
            BILI_PLAYURL_API,
            mapOf("bvid" to bvid, "cid" to cid.toString(), "fnval" to "16", "fourk" to "1"),
            mapOf("Referer" to "https://www.bilibili.com")
        ) ?: return null
        val data = parseJsonObject(text)?.obj("data") ?: return null
        val audio = data.obj("dash")?.array("audio")
        if (!audio.isNullOrEmpty()) {
            val best = audio.mapNotNull { it as? JsonObject }.maxByOrNull { item ->
                item["bandwidth"]?.asLongOrNull() ?: item["id"]?.asLongOrNull() ?: 0L
            }
            val url = best?.string("baseUrl")?.ifBlank { best.string("base_url") }
            if (!url.isNullOrBlank()) return url.replace("http://", "https://")
        }
        val durl = data.array("durl")
        val first = durl?.firstOrNull() as? JsonObject
        val url = first?.string("url")
        if (!url.isNullOrBlank()) return url.replace("http://", "https://")
        return null
    }

    override fun getLyric(info: MusicInfo): String? = null

    override fun getPicUrl(info: MusicInfo): String? = info.img

    override fun getDownloadHeaders(): Map<String, String> = mapOf("Referer" to "https://www.bilibili.com")

    override fun getDownloadCookies(): Map<String, String> {
        ensureCookies()
        return http.cookieHeader().split(";").mapNotNull { part ->
            val index = part.indexOf('=')
            if (index <= 0) return@mapNotNull null
            part.substring(0, index).trim() to part.substring(index + 1).trim()
        }.toMap()
    }

    private fun ensureCookies() {
        if (cookiesReady) return
        cookiesReady = true
        try {
            http.getText("https://www.bilibili.com", headers = mapOf("Referer" to "https://www.bilibili.com"))
        } catch (_: Exception) {
            // fall back to a generated buvid3 below
        }
        if (http.cookieValue("buvid3").isNullOrBlank()) {
            http.setCookie(
                "buvid3",
                UUID.randomUUID().toString().replace("-", "") + "infoc",
                ".bilibili.com"
            )
        }
    }

    private fun getWbiKeys(): Pair<String, String>? {
        val cached = wbiKeys
        if (cached != null && System.currentTimeMillis() < wbiExpireAt) return cached
        val text = http.getText(BILI_NAV_API) ?: return null
        val body = parseJsonObject(text) ?: return null
        val wbi = body.obj("data")?.obj("wbi_img") ?: return null
        val imgKey = extractKey(wbi.string("img_url"))
        val subKey = extractKey(wbi.string("sub_url"))
        if (imgKey.isBlank() || subKey.isBlank()) return null
        val keys = Pair(imgKey, subKey)
        wbiKeys = keys
        wbiExpireAt = System.currentTimeMillis() + 6L * 3600L * 1000L
        return keys
    }

    private fun extractKey(url: String): String {
        if (url.isBlank()) return ""
        val name = url.substringAfterLast('/').substringBefore('.')
        return name
    }

    private fun getCid(bvid: String): Long? {
        val cached = cidCache[bvid]
        if (cached != null) return cached
        val text = http.getText(BILI_PAGELIST_API, mapOf("bvid" to bvid)) ?: return null
        val pages = parseJsonObject(text)?.array("data") ?: return null
        val cid = (pages.firstOrNull() as? JsonObject)?.asLongOrNull("cid") ?: return null
        if (cid > 0) cidCache[bvid] = cid
        return cid
    }

    private fun parseSearchResult(items: kotlinx.serialization.json.JsonArray): List<MusicInfo> {
        val results = mutableListOf<MusicInfo>()
        for (element in items) {
            val item = element as? JsonObject ?: continue
            try {
                val bvid = item.string("bvid")
                if (bvid.isBlank()) continue
                val title = TITLE_TAG_RE.replace(item.string("title"), "").trim()
                results.add(
                    MusicInfo(
                        name = Crypto.decodeName(title),
                        singer = item.string("author"),
                        source = sourceId,
                        songmid = bvid,
                        interval = parseDuration(item.string("duration")),
                        img = item.string("pic").replace("http://", "https://").ifBlank { null },
                        playCount = item["play"]?.asLongOrNull() ?: 0L
                    )
                )
            } catch (_: Exception) {
                // skip malformed item
            }
        }
        return results
    }

    private fun parseDuration(raw: String): Int {
        if (raw.isBlank()) return 0
        val parts = raw.trim().split(":").mapNotNull { it.toIntOrNull() }
        if (parts.isEmpty() || parts.size > 3) return 0
        var seconds = 0
        for (part in parts) seconds = seconds * 60 + part
        return seconds
    }

    private fun JsonObject.asLongOrNull(key: String): Long? = this[key]?.asLongOrNull()

    companion object {
        private const val BILI_SEARCH_API = "https://api.bilibili.com/x/web-interface/wbi/search/type"
        private const val BILI_NAV_API = "https://api.bilibili.com/x/web-interface/nav"
        private const val BILI_PAGELIST_API = "https://api.bilibili.com/x/player/pagelist"
        private const val BILI_PLAYURL_API = "https://api.bilibili.com/x/player/playurl"
        private val TITLE_TAG_RE = Regex("<[^>]+>")
    }
}
