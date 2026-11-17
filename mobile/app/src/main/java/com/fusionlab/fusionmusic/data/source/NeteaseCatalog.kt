package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.durationMatches
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.net.array
import com.fusionlab.fusionmusic.data.net.int
import com.fusionlab.fusionmusic.data.net.jsonObject
import com.fusionlab.fusionmusic.data.net.listObjects
import com.fusionlab.fusionmusic.data.net.long
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class ArtistRef(val id: String, val name: String)

data class ArtistInfo(
    val id: String,
    val name: String,
    val cover: String = "",
    val alias: List<String> = emptyList(),
    val briefDesc: String = "",
    val musicSize: Int = 0,
    val albumSize: Int = 0,
    val mvSize: Int = 0,
    val fansSize: Int = 0,
    val hotSongs: List<MusicInfo> = emptyList()
)

data class AlbumInfo(
    val id: String,
    val name: String,
    val cover: String = "",
    val artists: List<ArtistRef> = emptyList(),
    val artistNames: String = "",
    val publishText: String = "",
    val company: String = "",
    val typeText: String = "",
    val version: String = "",
    val size: Int = 0,
    val description: String = "",
    val songs: List<MusicInfo> = emptyList()
)

data class WikiRow(val label: String, val value: String)

data class WikiPage(val songId: String = "", val rows: List<WikiRow> = emptyList())

/**
 * 网易云「按名字定位」的歌手、专辑与歌曲百科。
 *
 * 其它音源没有网易云的歌手/专辑/歌曲 id，所以入口只给名字时先搜一次，
 * 再按名称与时长核对。所有结果都来自 eapi，不额外引入第三方接口。
 */
class NeteaseCatalog(private val sourceProvider: () -> NeteaseSource?) {
    private val source: NeteaseSource
        get() = sourceProvider() ?: error("网易云音源不可用")
    private val artistCache = java.util.concurrent.ConcurrentHashMap<String, ArtistInfo>()
    private val albumCache = java.util.concurrent.ConcurrentHashMap<String, AlbumInfo>()
    private val wikiCache = java.util.concurrent.ConcurrentHashMap<String, WikiPage>()

    fun searchArtists(keyword: String, limit: Int = 10): List<ArtistRef> {
        val query = keyword.trim()
        if (query.isEmpty()) return emptyList()
        val data = jsonObject(
            "s" to JsonPrimitive(query),
            "type" to JsonPrimitive(100),
            "limit" to JsonPrimitive(limit.coerceIn(1, 30)),
            "offset" to JsonPrimitive(0)
        )
        val response = source.eapi("/api/search/get", data) ?: return emptyList()
        val artists = response.obj("result")?.listObjects("artists") ?: return emptyList()
        return artists.mapNotNull { item ->
            val id = item.string("id")
            if (id.isBlank()) null else ArtistRef(id, Crypto.decodeName(item.string("name")))
        }
    }

    fun artistPage(id: String = "", name: String = ""): ArtistInfo? {
        val artistId = id.trim()
        val artistName = name.trim()
        if (artistId.isBlank() && artistName.isBlank()) return null
        if (artistId.isNotBlank()) artistCache[artistId]?.let { return it }
        val match = if (artistName.isNotBlank()) pickArtist(searchArtists(artistName, 5), artistName) else null
        val resolvedId = artistId.ifBlank { match?.id ?: "" }
        if (resolvedId.isBlank()) return null
        val response = source.eapi("/api/v1/artist/" + resolvedId, JsonObject(emptyMap())) ?: return null
        val artist = response.obj("artist") ?: JsonObject(emptyMap())
        if (artist.isEmpty() && match == null) return null
        val hotSongs = try {
            source.parseSongDetailSongs(response.array("hotSongs") ?: JsonArray(emptyList()))
        } catch (_: Exception) {
            emptyList()
        }
        val alias = artist.array("alias")?.mapNotNull { element ->
            (element as? JsonPrimitive)?.content
        } ?: emptyList()
        val page = ArtistInfo(
            id = artist.string("id").ifBlank { resolvedId },
            name = Crypto.decodeName(artist.string("name").ifBlank { match?.name ?: artistName }),
            cover = artist.string("picUrl"),
            alias = alias,
            briefDesc = artist.string("briefDesc"),
            musicSize = artist.int("musicSize"),
            albumSize = artist.int("albumSize"),
            mvSize = artist.int("mvSize"),
            fansSize = 0,
            hotSongs = hotSongs
        )
        if (artistCache.size > 80) artistCache.clear()
        artistCache[page.id] = page
        return page
    }

    fun searchAlbums(keyword: String, limit: Int = 10): List<AlbumInfo> {
        val query = keyword.trim()
        if (query.isEmpty()) return emptyList()
        val data = jsonObject(
            "s" to JsonPrimitive(query),
            "type" to JsonPrimitive(10),
            "limit" to JsonPrimitive(limit.coerceIn(1, 30)),
            "offset" to JsonPrimitive(0)
        )
        val response = source.eapi("/api/search/get", data) ?: return emptyList()
        val albums = response.obj("result")?.listObjects("albums") ?: return emptyList()
        return albums.mapNotNull { item ->
            val id = item.string("id")
            if (id.isBlank()) return@mapNotNull null
            val artist = item.obj("artist")
            AlbumInfo(
                id = id,
                name = Crypto.decodeName(item.string("name")),
                cover = item.string("picUrl"),
                artists = listOfNotNull(
                    artist?.let { ArtistRef(it.string("id"), Crypto.decodeName(it.string("name"))) }
                ),
                artistNames = Crypto.decodeName(artist?.string("name") ?: ""),
                publishText = formatDate(item.long("publishTime")),
                company = item.string("company"),
                size = item.int("size")
            )
        }
    }

    fun albumPage(id: String = "", name: String = "", artist: String = ""): AlbumInfo? {
        val albumId = id.trim()
        val albumName = name.trim()
        if (albumId.isBlank() && albumName.isBlank()) return null
        if (albumId.isNotBlank()) albumCache[albumId]?.let { return it }
        var resolvedId = albumId
        if (resolvedId.isBlank()) {
            val picked = pickAlbum(searchAlbums(albumName, 10), albumName) ?: return null
            resolvedId = picked.id
        }
        val response = source.eapi("/api/v1/album/" + resolvedId, JsonObject(emptyMap())) ?: return null
        val album = response.obj("album") ?: return null
        if (album.isEmpty()) return null
        val nameMatches = albumName.isBlank() || sameTitle(album.string("name"), albumName)
        if (albumId.isNotBlank() && !nameMatches && albumName.isNotBlank()) {
            return albumPage("", albumName, artist)
        }
        val rawArtists = album.array("artists") ?: album.array("artist") ?: JsonArray(emptyList())
        val refs = rawArtists.mapNotNull { element ->
            val item = element as? JsonObject ?: return@mapNotNull null
            ArtistRef(item.string("id"), Crypto.decodeName(item.string("name")))
        }
        val publish = album.long("publishTime")
        val songs = try {
            source.parseSongDetailSongs(response.array("songs") ?: JsonArray(emptyList()))
        } catch (_: Exception) {
            emptyList()
        }
        val page = AlbumInfo(
            id = album.string("id").ifBlank { resolvedId },
            name = Crypto.decodeName(album.string("name").ifBlank { albumName }),
            cover = album.string("picUrl"),
            artists = refs,
            artistNames = refs.joinToString("、") { it.name },
            publishText = formatDate(publish),
            company = album.string("company"),
            typeText = albumType(album.string("type")),
            version = album.string("subType"),
            size = album.int("size"),
            description = album.string("description").ifBlank { album.string("briefDesc") },
            songs = songs
        )
        if (albumCache.size > 80) albumCache.clear()
        albumCache[page.id] = page
        return page
    }

    fun songWiki(
        songId: String = "",
        name: String = "",
        singer: String = "",
        albumName: String = "",
        albumId: String = "",
        interval: Int = 0
    ): WikiPage {
        var id = songId.trim()
        var resolvedAlbumId = albumId.trim()
        var resolvedAlbum = albumName.trim()
        if (id.isBlank()) {
            val matched = searchSongMatch(name, singer, interval) ?: return WikiPage()
            id = matched.songmid
            if (resolvedAlbumId.isBlank()) resolvedAlbumId = matched.albumId
            if (resolvedAlbum.isBlank()) resolvedAlbum = matched.albumName
        }
        if (id.isBlank()) return WikiPage()
        wikiCache[id]?.let { return it }
        val response = source.eapi(
            "/api/song/play/about/block/page",
            jsonObject("songId" to JsonPrimitive(id))
        ) ?: return WikiPage()
        val release = songRelease(resolvedAlbumId, resolvedAlbum, singer)
        val page = WikiPage(id, parseWikiRows(response, release))
        if (response["data"] != null) {
            if (wikiCache.size > 120) wikiCache.clear()
            wikiCache[id] = page
        }
        return page
    }

    private fun searchSongMatch(name: String, singer: String, interval: Int): MusicInfo? {
        if (name.isBlank()) return null
        val keyword = (name + " " + singer).trim()
        val songs = try {
            source.search(keyword, 1, 10)
        } catch (_: Exception) {
            emptyList()
        }
        return pickWikiSong(songs, name, interval)
    }

    private fun pickWikiSong(songs: List<MusicInfo>, name: String, interval: Int): MusicInfo? {
        if (songs.isEmpty() || name.isBlank()) return null
        val wanted = normalize(name)
        val exact = mutableListOf<MusicInfo>()
        val loose = mutableListOf<MusicInfo>()
        for (song in songs) {
            if (!sameTitle(song.name, name)) continue
            if (normalize(song.name) != wanted && interval <= 0) continue
            if (!durationMatches(song, interval)) continue
            if (normalize(song.name) == wanted) exact.add(song) else loose.add(song)
        }
        return (exact + loose).firstOrNull()
    }

    private fun parseWikiRows(payload: JsonObject, release: Pair<String, String>): List<WikiRow> {
        val values = HashMap<String, MutableList<String>>()
        val labels = HashMap<String, String>()
        val blocks = payload.obj("data")?.array("blocks") ?: JsonArray(emptyList())
        for (element in blocks) {
            val block = element as? JsonObject ?: continue
            if (block.string("code") != "SONG_PLAY_ABOUT_SONG_BASIC") continue
            for (creativeElement in block.array("creatives") ?: JsonArray(emptyList())) {
                val creative = creativeElement as? JsonObject ?: continue
                val key = creative.string("creativeType")
                if (key.isBlank()) continue
                val ui = creative.obj("uiElement") ?: JsonObject(emptyMap())
                val label = nodeTitle(ui)
                if (label.isNotBlank() && !labels.containsKey(key)) labels[key] = label
                val found = mutableListOf<String>()
                for (link in ui.array("textLinks") ?: JsonArray(emptyList())) {
                    val text = (link as? JsonObject)?.string("text") ?: ""
                    if (text.isNotBlank()) found.add(text)
                }
                for (res in creative.array("resources") ?: JsonArray(emptyList())) {
                    val title = nodeTitle((res as? JsonObject)?.obj("uiElement") ?: JsonObject(emptyMap()))
                    if (title.isNotBlank()) found.add(title)
                }
                if (found.isNotEmpty()) values.getOrPut(key) { mutableListOf() }.addAll(found)
            }
        }
        if (release.first.isNotBlank()) values["release_time"] = mutableListOf(release.first)
        if (release.second.isNotBlank()) values["release_version"] = mutableListOf(release.second)

        val rows = mutableListOf<WikiRow>()
        for ((key, defaultLabel) in WIKI_FIELDS) {
            val items = values[key]?.map { it.trim() }?.filter { it.isNotBlank() } ?: continue
            if (items.isEmpty()) continue
            val text = if (key == "songTag") {
                items.joinToString(" / ") { it.replaceFirst("-", "·") }
            } else {
                items.joinToString("、")
            }
            rows.add(WikiRow(labels[key] ?: defaultLabel, text))
        }
        return rows
    }

    private fun songRelease(albumId: String, albumName: String, artist: String): Pair<String, String> {
        val page = try {
            if (albumId.isNotBlank()) albumPage(albumId, "", artist) else null
        } catch (_: Exception) {
            null
        }
        val valid = page != null && (albumName.isBlank() || sameTitle(page.name, albumName))
        val resolved = if (valid) page else if (albumName.isNotBlank()) albumPage("", albumName, artist) else null
        if (resolved == null) return "" to ""
        return resolved.publishText to resolved.version.ifBlank { resolved.typeText }
    }

    private fun pickArtist(artists: List<ArtistRef>, name: String): ArtistRef? {
        if (artists.isEmpty()) return null
        val wanted = normalize(name)
        return artists.firstOrNull { normalize(it.name) == wanted }
            ?: artists.firstOrNull { normalize(it.name).contains(wanted) || wanted.contains(normalize(it.name)) }
            ?: artists.first()
    }

    private fun pickAlbum(albums: List<AlbumInfo>, name: String): AlbumInfo? {
        if (albums.isEmpty()) return null
        val wanted = normalize(name)
        val exact = albums.filter { normalize(it.name) == wanted }
        if (exact.isNotEmpty()) return exact.maxByOrNull { it.size }
        val loose = albums.filter {
            normalize(it.name).contains(wanted) || wanted.contains(normalize(it.name))
        }
        return loose.maxByOrNull { it.size } ?: albums.maxByOrNull { it.size }
    }

    private fun nodeTitle(node: JsonObject?): String {
        val main = node?.obj("mainTitle") ?: return ""
        return main.string("title").trim()
    }

    private fun albumType(raw: String): String = when (raw.trim().lowercase()) {
        "album" -> "专辑"
        "single" -> "单曲"
        "ep" -> "EP"
        "compilation" -> "精选集"
        "live" -> "现场"
        else -> raw
    }

    companion object {
        private val WIKI_FIELDS = listOf(
            "songTag" to "曲风",
            "language" to "语种",
            "release_time" to "发行时间",
            "release_version" to "发行版本",
            "bpm" to "BPM",
            "songBizTag" to "推荐标签",
            "songAward" to "获奖成就",
            "entertainment" to "影视节目",
            "songComment" to "乐评"
        )

        fun sameTitle(left: String, right: String): Boolean {
            val a = normalize(left)
            val b = normalize(right)
            if (a.isBlank() || b.isBlank()) return false
            return a == b || a.contains(b) || b.contains(a)
        }

        private fun normalize(text: String): String = text.filterNot { it.isWhitespace() }.lowercase(Locale.ROOT)

        private fun formatDate(millis: Long): String {
            if (millis <= 0L) return ""
            return try {
                SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date(millis))
            } catch (_: Exception) {
                ""
            }
        }
    }
}
