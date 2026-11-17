package com.fusionlab.fusionmusic.data.store

import android.content.Context
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.model.normalizeSingers
import com.fusionlab.fusionmusic.core.util.JsonFiles
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.io.File
import java.text.Collator
import java.util.Locale
import java.util.UUID

const val LIBRARY_SCHEMA_VERSION = 1
const val SORT_ADD_TIME_ASC = "add_time_asc"
const val SORT_ADD_TIME_DESC = "add_time_desc"
const val SORT_NAME_ASC = "name_asc"
const val SORT_NAME_DESC = "name_desc"
const val FAVORITES_PLAYLIST_ID = "__favorites__"
const val MAX_HISTORY_ENTRIES = 300

@Serializable
data class Playlist(
    val id: String = "",
    val name: String = "",
    val songs: List<Track> = emptyList(),
    @SerialName("created_at") val createdAt: Double = 0.0,
    @SerialName("updated_at") val updatedAt: Double = 0.0,
    @SerialName("sort_mode") val sortMode: String = SORT_ADD_TIME_DESC,
    @SerialName("is_system") val isSystem: Boolean = false
) {
    val count: Int get() = songs.size

    companion object {
        fun create(name: String, isSystem: Boolean = false): Playlist {
            val now = System.currentTimeMillis() / 1000.0
            return Playlist(
                id = "pl_" + UUID.randomUUID().toString().replace("-", "").take(10),
                name = name,
                createdAt = now,
                updatedAt = now,
                isSystem = isSystem
            )
        }
    }
}

@Serializable
data class PlaylistsFile(
    val version: Int = LIBRARY_SCHEMA_VERSION,
    val playlists: List<Playlist> = emptyList()
)

class LibraryStore(context: Context) {
    private val dataDir = File(context.filesDir, "data").apply { mkdirs() }
    private val playlistsFile = File(dataDir, "playlists.json")
    private val favoritesFile = File(dataDir, "favorites.json")
    private val historyFile = File(dataDir, "history.json")
    private val localFile = File(dataDir, "local.json")
    private val lock = Any()
    private val collator = Collator.getInstance(Locale.CHINA)
    private val listeners = mutableListOf<(String) -> Unit>()

    private var playlists: MutableList<Playlist> = mutableListOf()
    private var favorites: MutableList<Track> = mutableListOf()
    private var history: MutableList<Track> = mutableListOf()
    private var localTracks: MutableList<Track> = mutableListOf()

    init {
        load()
    }

    fun addListener(listener: (String) -> Unit) {
        listeners.add(listener)
    }

    fun removeListener(listener: (String) -> Unit) {
        listeners.remove(listener)
    }

    fun allPlaylists(): List<Playlist> = synchronized(lock) { playlists.toList() }

    fun userPlaylists(): List<Playlist> = synchronized(lock) { playlists.filter { !it.isSystem } }

    fun getPlaylist(id: String): Playlist? = synchronized(lock) { playlists.firstOrNull { it.id == id } }

    fun favoritesPlaylist(): Playlist? = synchronized(lock) { playlists.firstOrNull { it.id == FAVORITES_ID } }

    fun createPlaylist(name: String): Playlist = synchronized(lock) {
        val playlist = Playlist.create(name.ifBlank { "新建歌单" })
        playlists.add(playlist)
        saveAllLocked()
        notifyListeners("playlists")
        playlist
    }

    fun renamePlaylist(id: String, newName: String): Boolean = synchronized(lock) {
        val index = playlists.indexOfFirst { it.id == id && !it.isSystem }
        if (index < 0) return false
        val current = playlists[index]
        playlists[index] = current.copy(name = newName.ifBlank { "未命名歌单" }, updatedAt = now())
        saveAllLocked()
        notifyListeners("playlists")
        true
    }

    fun deletePlaylist(id: String): Boolean = synchronized(lock) {
        if (id == FAVORITES_ID) return false
        val removed = playlists.removeAll { it.id == id && !it.isSystem }
        if (removed) {
            saveAllLocked()
            notifyListeners("playlists")
        }
        removed
    }

    fun clearPlaylist(id: String): Boolean = synchronized(lock) {
        val index = playlists.indexOfFirst { it.id == id }
        if (index < 0) return false
        val current = playlists[index]
        playlists[index] = current.copy(songs = emptyList(), updatedAt = now())
        if (id == FAVORITES_ID) {
            favorites.clear()
            JsonFiles.writeAtomic(favoritesFile, favorites.toList())
        }
        saveAllLocked()
        notifyListeners("playlists")
        true
    }

    fun addToPlaylist(id: String, track: Track): Boolean = synchronized(lock) {
        val index = playlists.indexOfFirst { it.id == id }
        if (index < 0) return false
        val current = playlists[index]
        if (current.songs.any { it.sameSong(track) }) return false
        val updated = current.copy(songs = current.songs + track, updatedAt = now())
        playlists[index] = updated
        if (id == FAVORITES_ID && favorites.none { it.sameSong(track) }) {
            favorites.add(track)
            JsonFiles.writeAtomic(favoritesFile, favorites.toList())
        }
        saveAllLocked()
        notifyListeners("playlists")
        true
    }

    fun removeFromPlaylist(id: String, uid: String): Boolean = synchronized(lock) {
        val index = playlists.indexOfFirst { it.id == id }
        if (index < 0) return false
        val current = playlists[index]
        val filtered = current.songs.filterNot { it.uid == uid }
        if (filtered.size == current.songs.size) return false
        playlists[index] = current.copy(songs = filtered, updatedAt = now())
        if (id == FAVORITES_ID) {
            favorites.removeAll { it.uid == uid }
            JsonFiles.writeAtomic(favoritesFile, favorites.toList())
        }
        saveAllLocked()
        notifyListeners("playlists")
        true
    }

    fun moveInPlaylist(id: String, src: Int, dst: Int): Boolean = synchronized(lock) {
        val index = playlists.indexOfFirst { it.id == id }
        if (index < 0) return false
        val current = playlists[index]
        if (src !in current.songs.indices || dst !in current.songs.indices || src == dst) return false
        val songs = current.songs.toMutableList()
        val item = songs.removeAt(src)
        songs.add(dst, item)
        playlists[index] = current.copy(songs = songs, updatedAt = now())
        saveAllLocked()
        notifyListeners("playlists")
        true
    }

    fun setSortMode(id: String, mode: String): Boolean = synchronized(lock) {
        if (!SORT_MODES.contains(mode)) return false
        val index = playlists.indexOfFirst { it.id == id }
        if (index < 0) return false
        val current = playlists[index]
        playlists[index] = current.copy(sortMode = mode, updatedAt = now())
        saveAllLocked()
        notifyListeners("playlists")
        true
    }

    fun playlistsContaining(track: Track): List<String> = synchronized(lock) {
        playlists.filter { playlist ->
            !playlist.isSystem && playlist.songs.any { it.sameSong(track) }
        }.map { it.name }
    }

    fun isFavorite(track: Track): Boolean = synchronized(lock) {
        favorites.any { it.sameSong(track) }
    }

    fun toggleFavorite(track: Track): Boolean = synchronized(lock) {
        val existing = favorites.indexOfFirst { it.sameSong(track) }
        val added = existing < 0
        if (added) favorites.add(0, track) else favorites.removeAt(existing)
        JsonFiles.writeAtomic(favoritesFile, favorites.toList())
        val index = playlists.indexOfFirst { it.id == FAVORITES_ID }
        if (index >= 0) {
            playlists[index] = playlists[index].copy(songs = favorites.toList(), updatedAt = now())
        }
        saveAllLocked()
        notifyListeners("favorites")
        added
    }

    fun favorites(): List<Track> = synchronized(lock) { favorites.toList() }

    fun history(): List<Track> = synchronized(lock) { history.toList() }

    fun recordPlay(track: Track) = synchronized(lock) {
        history.removeAll { it.sameSong(track) }
        history.add(0, track)
        while (history.size > MAX_HISTORY) history.removeAt(history.size - 1)
        JsonFiles.writeAtomic(historyFile, history.toList())
        notifyListeners("history")
    }

    fun clearHistory() = synchronized(lock) {
        history.clear()
        JsonFiles.writeAtomic(historyFile, history.toList())
        notifyListeners("history")
    }

    fun localTracks(): List<Track> = synchronized(lock) { localTracks.toList() }

    fun addLocalTrack(track: Track) = synchronized(lock) {
        if (localTracks.none { it.uid == track.uid || (it.path.isNotBlank() && it.path == track.path) }) {
            localTracks.add(track)
            JsonFiles.writeAtomic(localFile, localTracks.toList())
            notifyListeners("local")
        }
    }

    fun setLocalTracks(tracks: List<Track>) = synchronized(lock) {
        localTracks.clear()
        localTracks.addAll(tracks)
        JsonFiles.writeAtomic(localFile, localTracks.toList())
        notifyListeners("local")
    }

    fun sortTracks(tracks: List<Track>, mode: String): List<Track> = when (mode) {
        SORT_ADD_TIME_ASC -> tracks.sortedBy { it.addedAt }
        SORT_NAME_ASC -> tracks.sortedWith { a, b -> collator.compare(a.name, b.name) }
        SORT_NAME_DESC -> tracks.sortedWith { a, b -> collator.compare(b.name, a.name) }
        else -> tracks.sortedByDescending { it.addedAt }
    }

    private fun load() = synchronized(lock) {
        val file = JsonFiles.read(playlistsFile, PlaylistsFile())
        playlists.clear()
        playlists.addAll(file.playlists.map { playlist ->
            playlist.copy(songs = playlist.songs.map { track -> track.copy(singer = normalizeSingers(track.singer)) })
        })
        if (playlists.none { it.id == FAVORITES_ID }) {
            playlists.add(0, Playlist.create("我喜欢的音乐", isSystem = true).copy(id = FAVORITES_ID))
        }
        favorites.clear()
        favorites.addAll(JsonFiles.read(favoritesFile, emptyList<Track>()).map { it.copy(singer = normalizeSingers(it.singer)) })
        history.clear()
        history.addAll(JsonFiles.read(historyFile, emptyList<Track>()).map { it.copy(singer = normalizeSingers(it.singer)) })
        localTracks.clear()
        localTracks.addAll(JsonFiles.read(localFile, emptyList<Track>()).map { it.copy(singer = normalizeSingers(it.singer)) })
        val favoritesIndex = playlists.indexOfFirst { it.id == FAVORITES_ID }
        if (favoritesIndex >= 0) {
            playlists[favoritesIndex] = playlists[favoritesIndex].copy(songs = favorites.toList())
        }
    }

    private fun saveAllLocked() {
        JsonFiles.writeAtomic(playlistsFile, PlaylistsFile(playlists = playlists.toList()))
    }

    private fun notifyListeners(what: String) {
        listeners.toList().forEach { listener ->
            runCatching { listener(what) }
        }
    }

    private fun now(): Double = System.currentTimeMillis() / 1000.0

    companion object {
        const val SCHEMA_VERSION = 1
        const val FAVORITES_ID = "__favorites__"
        const val HISTORY_ID = "__history__"
        const val MAX_HISTORY = 300
        const val SORT_ADD_TIME_ASC = "add_time_asc"
        const val SORT_ADD_TIME_DESC = "add_time_desc"
        const val SORT_NAME_ASC = "name_asc"
        const val SORT_NAME_DESC = "name_desc"
        val SORT_MODES = listOf(SORT_ADD_TIME_ASC, SORT_ADD_TIME_DESC, SORT_NAME_ASC, SORT_NAME_DESC)
    }
}
