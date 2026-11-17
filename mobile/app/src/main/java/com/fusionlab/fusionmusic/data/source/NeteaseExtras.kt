package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.asStringOrNull
import com.fusionlab.fusionmusic.data.net.int
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.listObjects
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

data class LyricBundle(
    val lrc: String = "",
    val translation: String = "",
    val roma: String = "",
    val word: String = "",
    val wordTranslation: String = "",
    val wordRoma: String = ""
) {
    val isEmpty: Boolean get() = lrc.isBlank() && word.isBlank()
}

data class DiscoverPlaylist(
    val id: String,
    val name: String,
    val cover: String,
    val playCount: Long,
    val trackCount: Int,
    val description: String
)

data class ToplistInfo(
    val id: String,
    val name: String,
    val cover: String,
    val updateFrequency: String,
    val trackCount: Int
)

data class HotSearch(
    val keyword: String,
    val score: Long
)

data class PlaylistInfo(
    val id: String,
    val name: String,
    val cover: String,
    val trackCount: Int,
    val playCount: Long,
    val creator: String,
    val description: String
)

class NeteaseExtras(private val source: NeteaseSource) {
    fun fetchLyricBundle(
        songId: String,
        wantTranslation: Boolean = true,
        wantRoma: Boolean = false,
        wantWord: Boolean = true
    ): LyricBundle? {
        if (songId.isBlank()) return null
        val data = jsonObject(
            "id" to JsonPrimitive(songId),
            "lv" to JsonPrimitive(-1),
            "tv" to JsonPrimitive(if (wantTranslation) -1 else 0),
            "rv" to JsonPrimitive(if (wantRoma) -1 else 0),
            "kv" to JsonPrimitive(-1)
        )
        val full = if (wantWord) {
            JsonObject(
                data.toMutableMap().apply {
                    put("yv", JsonPrimitive(-1))
                    put("ytv", JsonPrimitive(if (wantTranslation) -1 else 0))
                    put("yrv", JsonPrimitive(if (wantRoma) -1 else 0))
                }
            )
        } else {
            data
        }
        val response = source.eapi("/api/song/lyric", full) ?: return null
        if (response.int("code") != 200) return null
        val bundle = LyricBundle(
            lrc = pickLyric(response, "lrc"),
            translation = pickLyric(response, "tlyric"),
            roma = pickLyric(response, "romalrc"),
            word = pickLyric(response, "yrc"),
            wordTranslation = pickLyric(response, "ytlyric"),
            wordRoma = pickLyric(response, "yromalrc")
        )
        return if (bundle.isEmpty) null else bundle
    }

    fun fetchTranslation(songId: String, wantTranslation: Boolean = true, wantRoma: Boolean = false): Pair<String, String> {
        if (!wantTranslation && !wantRoma) return "" to ""
        val bundle = fetchLyricBundle(songId, wantTranslation, wantRoma, wantWord = false) ?: return "" to ""
        return bundle.translation to bundle.roma
    }

    fun recommendPlaylists(limit: Int = 30): List<DiscoverPlaylist> {
        val response = source.eapi(
            "/api/personalized/playlist",
            jsonObject(
                "limit" to JsonPrimitive(limit),
                "total" to JsonPrimitive(true),
                "n" to JsonPrimitive(1000)
            )
        ) ?: return emptyList()
        return response.listObjects("result").mapNotNull { item ->
            val id = item.string("id")
            if (id.isBlank()) return@mapNotNull null
            DiscoverPlaylist(
                id = id,
                name = item.string("name"),
                cover = item.string("picUrl"),
                playCount = item["playCount"]?.asStringOrNull()?.toLongOrNull() ?: 0L,
                trackCount = item.int("trackCount"),
                description = item.string("copywriter")
            )
        }
    }

    fun newSongs(limit: Int = 12): List<MusicInfo> {
        val response = source.eapi(
            "/api/personalized/newsong",
            jsonObject("limit" to JsonPrimitive(limit))
        ) ?: return emptyList()
        val songs = mutableListOf<JsonObject>()
        for (element in response.array("result") ?: JsonArray(emptyList())) {
            val item = element as? JsonObject ?: continue
            val song = item.obj("song")
            if (song != null) songs.add(song) else if (item.string("id").isNotBlank()) songs.add(item)
        }
        return source.parseSongDetailSongs(JsonArray(songs))
    }

    fun toplists(): List<ToplistInfo> {
        val response = source.eapi("/api/toplist/detail", JsonObject(emptyMap())) ?: return emptyList()
        return response.listObjects("list").mapNotNull { item ->
            val playlist = item.obj("playlist")
            val id = item.string("id").ifBlank { playlist?.string("id") ?: "" }
            if (id.isBlank()) return@mapNotNull null
            ToplistInfo(
                id = id,
                name = item.string("name"),
                cover = item.string("coverImgUrl").ifBlank { playlist?.string("coverImgUrl") ?: "" },
                updateFrequency = item.string("updateFrequency"),
                trackCount = item.int("trackCount")
            )
        }
    }

    fun hotSearches(): List<HotSearch> {
        for (path in listOf("/api/search/hot/detail", "/api/search/hot")) {
            val response = source.eapi(path, JsonObject(emptyMap())) ?: continue
            if (response.int("code") != 200) continue
            val data = response.obj("data") ?: response.obj("result")
            val items = data?.array("hots") ?: (data as? JsonArray)
            if (items == null) continue
            val out = items.mapNotNull { element ->
                val item = element as? JsonObject ?: return@mapNotNull null
                val keyword = item.string("searchWord").ifBlank { item.string("first") }
                if (keyword.isBlank()) return@mapNotNull null
                HotSearch(keyword, item["score"]?.asStringOrNull()?.toLongOrNull() ?: 0L)
            }
            if (out.isNotEmpty()) return out.take(20)
        }
        return emptyList()
    }

    fun dailyRecommend(): List<MusicInfo> {
        if (!source.isLoggedIn()) return emptyList()
        val response = source.eapi(
            "/api/v1/discovery/recommend/songs",
            jsonObject("limit" to JsonPrimitive(100))
        ) ?: return emptyList()
        val songs = response.obj("data")?.array("dailySongs") ?: response.array("recommend") ?: return emptyList()
        return source.parseSongDetailSongs(songs)
    }

    fun playlistTracks(playlistId: String): List<MusicInfo> = source.playlistTracks(playlistId) ?: emptyList()

    fun playlistMeta(playlistId: String): PlaylistInfo? {
        val meta = source.playlistMeta(playlistId) ?: return null
        return PlaylistInfo(
            id = meta.id,
            name = meta.name,
            cover = meta.coverUrl,
            trackCount = meta.trackCount,
            playCount = 0L,
            creator = meta.creator,
            description = meta.description
        )
    }

    fun roamBatch(size: Int = 15): List<Pair<MusicInfo, String>> {
        if (size <= 0) return emptyList()
        if (source.isLoggedIn()) {
            val fm = roamFromFm(size)
            if (fm.isNotEmpty()) return fm
            val daily = dailyRecommend()
            if (daily.isNotEmpty()) {
                return daily.shuffled().take(size).map { it to "每日推荐" }
            }
        }
        return newSongs(maxOf(size, 10)).take(size).map { it to "新歌推荐" }
    }

    fun searchSuggest(keyword: String, limit: Int = 8): List<String> {
        if (keyword.isBlank()) return emptyList()
        val response = source.eapi(
            "/api/search/suggest/keyword",
            jsonObject("s" to JsonPrimitive(keyword))
        ) ?: return emptyList()
        val allMatch = response.obj("result")?.array("allMatch") ?: return emptyList()
        val out = mutableListOf<String>()
        val seen = mutableSetOf<String>()
        for (element in allMatch) {
            val item = element as? JsonObject ?: continue
            val word = item.string("keyword").trim()
            if (word.isBlank() || seen.contains(word)) continue
            seen.add(word)
            out.add(word)
            if (out.size >= limit.coerceAtLeast(1)) break
        }
        return out
    }

    private fun roamFromFm(size: Int): List<Pair<MusicInfo, String>> {
        val out = mutableListOf<Pair<MusicInfo, String>>()
        val seen = mutableSetOf<String>()
        val rounds = maxOf(1, (size + 2) / 3)
        repeat(rounds) {
            val response = source.eapi("/api/v1/radio/get", JsonObject(emptyMap())) ?: return@repeat
            val items = response.array("data") ?: return@repeat
            for (element in items) {
                val item = element as? JsonObject ?: continue
                val songId = item.string("id")
                if (songId.isBlank() || seen.contains(songId)) continue
                seen.add(songId)
                val parsed = source.parseSongDetailSongs(JsonArray(listOf(item)))
                if (parsed.isNotEmpty()) out.add(parsed[0] to item.string("reason"))
                if (out.size >= size) return out
            }
        }
        return out
    }

    private fun pickLyric(response: JsonObject, key: String): String {
        val node = response[key] ?: return ""
        if (node is JsonObject) return node.string("lyric")
        return node.jsonPrimitive.content
    }
}
