package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.QualityLevel
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.net.HttpEngine
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.bool
import com.fusionlab.fusionmusic.data.net.int
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.listObjects
import com.fusionlab.fusionmusic.data.net.long
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.parseJsonObject
import com.fusionlab.fusionmusic.data.net.string
import com.fusionlab.fusionmusic.data.net.stringList
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull

class NeteaseSource(
    timeoutSeconds: Int,
    proxy: String,
    log: AppLog?
) : BaseMusicSource("wy", "网易云音乐", timeoutSeconds, proxy, log) {
    override val searchLimit: Int = 20

    init {
        http.setCookie("os", "pc", ".music.163.com")
        http.setCookie("appver", "2.10.6", ".music.163.com")
        http.setCookie("channel", "netease", ".music.163.com")
        http.setCookie("_ntes_nuid", Crypto.randomHex(32), ".music.163.com")
        http.setCookie("__remember_me", "true", ".music.163.com")
    }

    override fun search(keyword: String, page: Int, limit: Int): List<MusicInfo> {
        val data = jsonObject(
            "keyword" to JsonPrimitive(keyword),
            "needCorrect" to JsonPrimitive("1"),
            "channel" to JsonPrimitive("typing"),
            "offset" to JsonPrimitive(limit.coerceAtMost(searchLimit) * (page - 1)),
            "scene" to JsonPrimitive("normal"),
            "total" to JsonPrimitive(if (page == 1) "true" else "false"),
            "limit" to JsonPrimitive(limit.coerceAtMost(searchLimit))
        )
        val response = eapi("/api/search/song/list/page", data) ?: return emptyList()
        if (response.int("code") != 200) return emptyList()
        val payload = response.obj("data") ?: return emptyList()
        setSearchTotal(payload["totalCount"]?.jsonPrimitive?.content)
        val parsed = parseSearchResult(payload.array("resources") ?: JsonArray(emptyList()))
        markOriginal(parsed)
        return parsed
    }

    override fun getMusicUrl(info: MusicInfo, quality: String): String? {
        val songId = info.songmid
        if (songId.isBlank()) return null
        val br = WY_QUALITY_BR[quality] ?: WY_QUALITY_BR[QualityLevel.LOW]!!
        val wantedRank = WY_QUALITY_RANK[quality] ?: 0

        try {
            val response = eapi(
                "/api/song/enhance/player/url",
                jsonObject(
                    "ids" to JsonPrimitive("[" + songId + "]"),
                    "br" to JsonPrimitive(br)
                )
            )
            val item = response?.array("data")?.firstOrNull() as? JsonObject
            val url = item?.string("url")
            if (!url.isNullOrBlank() && servedRank(item) >= wantedRank) return url
        } catch (_: Exception) {
            // fall through to the v1 route
        }

        try {
            val level = WY_REQUEST_LEVEL[quality] ?: "standard"
            val encodeType = if ((WY_QUALITY_RANK[quality] ?: 0) >= 3) "flac" else "mp3"
            val response = weapi(
                "/song/enhance/player/url/v1",
                jsonObject(
                    "ids" to JsonPrimitive("[" + songId + "]"),
                    "level" to JsonPrimitive(level),
                    "encodeType" to JsonPrimitive(encodeType)
                )
            )
            val item = response?.array("data")?.firstOrNull() as? JsonObject
            val url = item?.string("url")
            if (!url.isNullOrBlank() && servedRank(item) >= wantedRank) return url
        } catch (_: Exception) {
            // no address on this route
        }
        return null
    }

    override fun getLyric(info: MusicInfo): String? {
        val response = eapi(
            "/api/song/lyric",
            jsonObject(
                "id" to JsonPrimitive(info.songmid),
                "lv" to JsonPrimitive(-1),
                "tv" to JsonPrimitive(-1),
                "rv" to JsonPrimitive(-1)
            )
        ) ?: return null
        if (response.int("code") != 200) return null
        val lrc = response["lrc"] ?: response.obj("data")?.get("lrc")
        if (lrc is JsonObject) return lrc.string("lyric")
        return lrc?.jsonPrimitive?.content
    }

    override fun getPicUrl(info: MusicInfo): String? {
        if (info.img?.isNotBlank() == true) return info.img
        val response = weapi(
            "/song/detail",
            jsonObject("ids" to JsonPrimitive("[" + info.songmid + "]"))
        ) ?: return null
        val song = response.array("songs")?.firstOrNull() as? JsonObject ?: return null
        val album = song.obj("al") ?: return null
        return album.string("picUrl").ifBlank { null }
    }

    fun eapi(path: String, data: JsonObject): JsonObject? {
        val signed = Crypto.wyEapi(path, data)
        return try {
            http.postForm(EAPI_BASE + path, signed, commonHeaders()).use { response ->
                if (!response.isSuccessful) return null
                parseJsonObject(response.body?.string())
            }
        } catch (error: Exception) {
            log?.w("Netease", "eapi " + path + " failed: " + error.message)
            null
        }
    }

    fun weapi(path: String, data: JsonObject, base: String = WY_API_BASE): JsonObject? {
        val signed = Crypto.wyWeapi(data)
        return try {
            http.postForm(base + path, signed, commonHeaders()).use { response ->
                if (!response.isSuccessful) return null
                parseJsonObject(response.body?.string())
            }
        } catch (error: Exception) {
            log?.w("Netease", "weapi " + path + " failed: " + error.message)
            null
        }
    }

    fun loginQrKey(): String? {
        val response = eapi("/api/login/qrcode/unikey", jsonObject("type" to JsonPrimitive(1))) ?: return null
        if (response.int("code") != 200) return null
        return response.string("unikey").ifBlank { null }
    }

    fun loginQrCheck(key: String): QrCheck {
        val response = eapi(
            "/api/login/qrcode/client/login",
            jsonObject("key" to JsonPrimitive(key), "type" to JsonPrimitive(1))
        ) ?: return QrCheck(-1, "网络错误")
        val code = response.int("code")
        val message = response.string("message")
        val cookie = response.string("cookie").ifBlank { null }
        if (!cookie.isNullOrBlank()) applyCookie(cookie)
        return QrCheck(code, message, cookie)
    }

    fun applyCookie(cookie: String) {
        http.applyCookieString(cookie, ".music.163.com")
    }

    fun cookieString(): String = http.cookieHeader()

    fun isLoggedIn(): Boolean = !http.cookieValue("MUSIC_U").isNullOrBlank()

    fun cookieExpiry(): Long? = http.cookieExpiry("MUSIC_U")

    fun clearLogin() {
        http.clearCookies(setOf("os", "appver", "channel", "_ntes_nuid", "__remember_me"))
    }

    fun fetchProfile(): NeteaseProfile? {
        val response = eapi("/api/nuser/account/get", JsonObject(emptyMap())) ?: return null
        if (response.int("code") != 200) return null
        val profile = response.obj("profile") ?: return null
        val rights = profile.obj("vipRights")
        return NeteaseProfile(
            nickname = profile.string("nickname"),
            avatarUrl = profile.string("avatarUrl"),
            userId = profile.long("userId"),
            vipType = profile.int("vipType"),
            hasMusicPackage = rights?.obj("associator") != null,
            redVipLevel = profile.int("redVipLevel")
        )
    }

    fun refreshLogin(): String? {
        val response = eapi("/api/login/token/refresh", JsonObject(emptyMap())) ?: return null
        if (response.int("code") != 200) return null
        return cookieString().ifBlank { null }
    }

    fun loginState(): String {
        if (!isLoggedIn()) return "expired"
        val profile = fetchProfile() ?: return "offline"
        return if (profile.userId > 0) "ok" else "expired"
    }

    fun userPlaylists(): List<RemotePlaylist>? {
        val profile = fetchProfile() ?: return null
        val uid = profile.userId
        if (uid <= 0) return null
        val data = jsonObject(
            "uid" to JsonPrimitive(uid),
            "limit" to JsonPrimitive(2000),
            "offset" to JsonPrimitive(0)
        )
        val response = eapi("/api/user/playlist", data) ?: return null
        if (response.int("code") != 200) return null
        val items = response.listObjects("playlist")
        val result = mutableListOf<RemotePlaylist>()
        for (item in items) {
            val creator = item.obj("creator") ?: continue
            if (creator.long("userId") != uid) continue
            result.add(
                RemotePlaylist(
                    id = item.string("id"),
                    name = Crypto.decodeName(item.string("name")),
                    trackCount = item.int("trackCount"),
                    coverUrl = item.string("coverImgUrl")
                )
            )
        }
        return result
    }

    fun playlistTracks(playlistId: String): List<MusicInfo>? {
        if (playlistId.isBlank()) return null
        val pid = playlistId.toLongOrNull() ?: return null
        val response = eapi(
            "/api/v6/playlist/detail",
            jsonObject(
                "id" to JsonPrimitive(pid),
                "n" to JsonPrimitive(100000),
                "s" to JsonPrimitive(8)
            )
        ) ?: return null
        if (response.int("code") != 200) return null
        val playlist = response.obj("playlist") ?: return null
        val tracks = playlist.array("tracks") ?: return null
        return parseSongDetailSongs(tracks)
    }

    fun playlistMeta(playlistId: String): PlaylistMeta? {
        val pid = playlistId.toLongOrNull() ?: return null
        val response = eapi(
            "/api/v6/playlist/detail",
            jsonObject(
                "id" to JsonPrimitive(pid),
                "n" to JsonPrimitive(1),
                "s" to JsonPrimitive(8)
            )
        ) ?: return null
        val playlist = response.obj("playlist") ?: return null
        return PlaylistMeta(
            id = playlist.string("id"),
            name = Crypto.decodeName(playlist.string("name")),
            coverUrl = playlist.string("coverImgUrl"),
            trackCount = playlist.int("trackCount"),
            creator = Crypto.decodeName(playlist.obj("creator")?.string("nickname") ?: ""),
            description = playlist.string("description")
        )
    }

    fun parseSongDetailSongs(songs: JsonArray): List<MusicInfo> {
        val results = mutableListOf<MusicInfo>()
        for (element in songs) {
            val song = element as? JsonObject ?: continue
            try {
                val artists = song.array("ar") ?: song.array("artists") ?: JsonArray(emptyList())
                val singer = artists.mapNotNull { artist ->
                    (artist as? JsonObject)?.string("name")?.let { Crypto.formatSinger(Crypto.decodeName(it)) }
                }.joinToString("、")
                val album = song.obj("al") ?: song.obj("album") ?: JsonObject(emptyMap())
                val durationMs = song.long("dt").takeIf { it > 0 } ?: song.long("duration")
                val interval = if (durationMs > 0) (durationMs / 1000).toInt() else 0
                val types = parseTypes(song)
                results.add(
                    MusicInfo(
                        name = Crypto.decodeName(song.string("name")),
                        singer = singer,
                        source = sourceId,
                        songmid = song.string("id"),
                        albumName = Crypto.decodeName(album.string("name")),
                        albumId = album.string("id"),
                        interval = interval,
                        img = album.string("picUrl").ifBlank { null },
                        types = types.first,
                        typeDetail = types.second,
                        publishTime = song.long("publishTime"),
                        fee = song.obj("privilege")?.int("fee") ?: 0
                    )
                )
            } catch (_: Exception) {
                // skip malformed item
            }
        }
        return results
    }

    private fun parseSearchResult(resources: JsonArray): List<MusicInfo> {
        val results = mutableListOf<MusicInfo>()
        for (element in resources) {
            val item = element as? JsonObject ?: continue
            try {
                val base = item.obj("baseInfo") ?: continue
                val simple = base.obj("simpleSongData") ?: continue
                val artists = simple.array("ar") ?: JsonArray(emptyList())
                val singer = artists.mapNotNull { artist ->
                    (artist as? JsonObject)?.string("name")?.let { Crypto.formatSinger(Crypto.decodeName(it)) }
                }.joinToString("、")
                val album = simple.obj("al") ?: JsonObject(emptyMap())
                val intervalMs = simple.long("dt")
                val origin = simple.obj("originSongSimpleData")
                val originArtists = origin?.array("artists")?.mapNotNull { artist ->
                    (artist as? JsonObject)?.string("name")?.let { Crypto.formatSinger(Crypto.decodeName(it)) }
                } ?: emptyList()
                val types = parseTypes(simple)
                results.add(
                    MusicInfo(
                        name = Crypto.decodeName(simple.string("name")),
                        singer = singer,
                        source = sourceId,
                        songmid = simple.string("id"),
                        albumName = Crypto.decodeName(album.string("name")),
                        albumId = album.string("id"),
                        interval = if (intervalMs > 0) (intervalMs / 1000).toInt() else 0,
                        img = album.string("picUrl").ifBlank { null },
                        types = types.first,
                        typeDetail = types.second,
                        publishTime = simple.long("publishTime"),
                        isOriginal = false,
                        originSongId = origin?.string("songId") ?: "",
                        originArtists = originArtists,
                        originalName = originArtists.joinToString("、"),
                        fee = simple.obj("privilege")?.int("fee") ?: 0
                    )
                )
            } catch (_: Exception) {
                // skip malformed item
            }
        }
        return results
    }

    /**
     * 在结果页里按「同曲簇 + 被翻唱引用 + 有效发布日期」标记原唱。
     *
     * 这是桌面端完整规则的轻量版：不依赖策展表，也不额外请求专辑日期。
     * 被翻唱引用的锚点优先；没有引用时取无 origin 的干净锚点；再退到
     * 发布日期最早者。全部都是翻唱（原曲不在结果页）时不标记。
     */
    private fun markOriginal(items: List<MusicInfo>) {
        if (items.isEmpty()) return
        for (item in items) item.isOriginal = false
        val groups = LinkedHashMap<String, MutableList<MusicInfo>>()
        for (item in items) {
            val key = normalizedSongName(item.name)
            if (key.isBlank()) continue
            groups.getOrPut(key) { mutableListOf() }.add(item)
        }
        for (group in groups.values) {
            val anchors = group.filter { it.originSongId.isBlank() }
            if (anchors.isEmpty()) continue
            val referencedIds = group.mapNotNull { it.originSongId.takeIf { id -> id.isNotBlank() } }.toSet()
            val referenced = anchors.filter { it.songmid in referencedIds }
            val candidate = pickOriginal(referenced.ifEmpty { anchors })
            if (candidate != null) candidate.isOriginal = true
        }
    }

    private fun pickOriginal(items: List<MusicInfo>): MusicInfo? {
        return items.sortedWith(
            compareBy(
                { if (it.fee == 8) 1 else 0 },
                { if (validPublishTime(it.publishTime)) 0 else 1 },
                { publishMillis(it.publishTime) }
            )
        ).firstOrNull()
    }

    private fun normalizedSongName(name: String): String {
        var text = name.replace(Regex("[（(\\[【].*?[）)\\]】]"), " ")
        for (marker in listOf("live", "伴奏", "翻唱", "remix", "demo", "instrumental")) {
            text = text.replace(marker, " ", ignoreCase = true)
        }
        return text.filterNot { it.isWhitespace() }.lowercase()
    }

    private fun publishMillis(value: Long): Long {
        if (value <= 0L) return Long.MAX_VALUE
        return if (value > 10_000_000_000L) value else value * 1000L
    }

    private fun validPublishTime(value: Long): Boolean {
        val millis = publishMillis(value)
        if (millis == Long.MAX_VALUE) return false
        return try {
            val calendar = java.util.Calendar.getInstance()
            calendar.timeInMillis = millis
            val year = calendar.get(java.util.Calendar.YEAR)
            year >= 1975 && !(year >= 2000 && calendar.get(java.util.Calendar.MONTH) == 0 &&
                calendar.get(java.util.Calendar.DAY_OF_MONTH) == 1)
        } catch (_: Exception) {
            false
        }
    }

    private fun parseTypes(item: JsonObject): Pair<List<JsonObject>, Map<String, JsonObject>> {
        val privilege = item.obj("privilege") ?: JsonObject(emptyMap())
        val subs = mapOf(
            "flac24bit" to firstOf(item, "hr", "hires"),
            "flac" to firstOf(item, "sq", "sqMusic"),
            "320k" to firstOf(item, "h", "hMusic"),
            "128k" to firstOf(item, "l", "lMusic")
        )
        var top = WY_LEVEL_TO_QUALITY[privilege.string("playMaxBrLevel").ifBlank { privilege.string("maxBrLevel") }.lowercase()] ?: ""
        if (top.isBlank()) {
            val maxBr = privilege.long("maxbr").takeIf { it > 0 } ?: privilege.long("playMaxbr")
            for ((threshold, quality) in WY_MAXBR_TO_QUALITY) {
                if (maxBr >= threshold) {
                    top = quality
                    break
                }
            }
        }
        if (top.isBlank()) {
            top = listOf("flac24bit", "flac", "320k", "128k").firstOrNull { subs[it] != null } ?: ""
        }
        if (top.isBlank()) top = "128k"
        val topRank = WY_QUALITY_RANK[top] ?: 0
        val types = mutableListOf<JsonObject>()
        val details = LinkedHashMap<String, JsonObject>()
        for (quality in listOf("128k", "320k", "flac", "flac24bit")) {
            if ((WY_QUALITY_RANK[quality] ?: 0) > topRank) break
            types.add(jsonObject("type" to JsonPrimitive(quality)))
            val sub = subs[quality]
            details[quality] = jsonObject(
                "id" to JsonPrimitive(sub?.string("id")?.ifBlank { item.string("id") } ?: item.string("id"))
            )
        }
        return Pair(types, details)
    }

    private fun firstOf(item: JsonObject, vararg keys: String): JsonObject? {
        for (key in keys) {
            val value = item[key] as? JsonObject
            if (value != null) return value
        }
        return null
    }

    private fun servedRank(item: JsonObject?): Int {
        val level = item?.string("level")?.lowercase() ?: return 99
        return WY_LEVEL_RANK[level] ?: 99
    }

    private fun commonHeaders(): Map<String, String> = mapOf(
        "Referer" to "https://music.163.com",
        "Origin" to "https://music.163.com"
    )

    data class QrCheck(
        val code: Int,
        val message: String,
        val cookie: String? = null
    )

    data class NeteaseProfile(
        val nickname: String,
        val avatarUrl: String,
        val userId: Long,
        val vipType: Int,
        val hasMusicPackage: Boolean,
        val redVipLevel: Int
    )

    data class RemotePlaylist(
        val id: String,
        val name: String,
        val trackCount: Int,
        val coverUrl: String
    )

    data class PlaylistMeta(
        val id: String,
        val name: String,
        val coverUrl: String,
        val trackCount: Int,
        val creator: String,
        val description: String
    )

    companion object {
        const val EAPI_BASE = "https://interface3.music.163.com/eapi"
        const val WY_API_BASE = "https://music.163.com/weapi"
        const val WY_API_ALT_BASE = "https://music.163.com/api"

        private val WY_LEVEL_TO_QUALITY = mapOf(
            "standard" to "128k",
            "higher" to "128k",
            "exhigh" to "320k",
            "lossless" to "flac",
            "sky" to "flac",
            "jyeffect" to "flac",
            "hires" to "flac24bit",
            "jymaster" to "flac24bit"
        )
        private val WY_MAXBR_TO_QUALITY = listOf(
            1999000L to "flac24bit",
            999000L to "flac",
            320000L to "320k",
            128000L to "128k"
        )
        private val WY_QUALITY_BR = mapOf(
            "flac24bit" to 1999000,
            "flac" to 999000,
            "320k" to 320000,
            "128k" to 128000
        )
        private val WY_REQUEST_LEVEL = mapOf(
            "flac24bit" to "hires",
            "flac" to "lossless",
            "320k" to "exhigh",
            "128k" to "standard"
        )
        private val WY_LEVEL_RANK = mapOf(
            "standard" to 0, "higher" to 1, "exhigh" to 2,
            "lossless" to 3, "sky" to 3, "jyeffect" to 3,
            "hires" to 4, "jymaster" to 4
        )
        private val WY_QUALITY_RANK = mapOf("128k" to 0, "320k" to 2, "flac" to 3, "flac24bit" to 4)
    }
}
