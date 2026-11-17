package com.fusionlab.fusionmusic.playback

import com.fusionlab.fusionmusic.core.model.PlayMode
import com.fusionlab.fusionmusic.core.model.PlayQueue
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.lyrics.Lyrics
import com.fusionlab.fusionmusic.data.store.LibraryStore
import com.fusionlab.fusionmusic.data.store.SessionStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class PlaybackSnapshot(
    val current: Track? = null,
    val requested: Track? = null,
    val queue: List<Track> = emptyList(),
    val queueIndex: Int = -1,
    val playing: Boolean = false,
    val loading: Boolean = false,
    val positionMs: Long = 0L,
    val durationMs: Long = 0L,
    val quality: String = "",
    val fallbackSource: String = "",
    val error: String? = null,
    val lyrics: Lyrics = Lyrics(),
    val favorite: Boolean = false,
    val mode: PlayMode = PlayMode.LOOP_LIST,
    val loudnessText: String = ""
)

class PlaybackRepository(
    private val config: ConfigRepository,
    private val library: LibraryStore,
    private val sessionStore: SessionStore,
    private val scope: CoroutineScope
) {
    private val state = MutableStateFlow(PlaybackSnapshot())
    private var saveJob: Job? = null
    private var lastSavedAt = 0L

    val snapshot: StateFlow<PlaybackSnapshot> = state

    val queue: PlayQueue = PlayQueue { publishQueue() }

    init {
        queue.mode = PlayMode.fromName(config.getString("playback.mode", "loop_list"))
        restoreSession()
    }

    fun currentTrack(): Track? = state.value.current

    fun setLoading(value: Boolean) = update { it.copy(loading = value) }

    fun setPlaying(value: Boolean) = update { it.copy(playing = value) }

    fun setPosition(value: Long) {
        if (value == state.value.positionMs) return
        update { it.copy(positionMs = value.coerceAtLeast(0L)) }
        if (value - lastSavedAt >= 60_000L) {
            lastSavedAt = value
            scheduleSave()
        }
    }

    fun setDuration(value: Long) {
        if (value == state.value.durationMs) return
        update { it.copy(durationMs = value.coerceAtLeast(0L)) }
    }

    fun setQuality(value: String) = update { it.copy(quality = value) }

    fun setFallbackSource(value: String) = update { it.copy(fallbackSource = value) }

    fun setError(value: String?) = update { it.copy(error = value) }

    fun setLyrics(value: Lyrics) = update { it.copy(lyrics = value) }

    fun setLoudnessText(value: String) = update { it.copy(loudnessText = value) }

    fun setCurrent(track: Track?, requested: Track? = track) {
        update {
            it.copy(
                current = track,
                requested = requested,
                durationMs = (track?.interval ?: 0) * 1000L,
                positionMs = 0L,
                error = null,
                favorite = track?.let { t -> library.isFavorite(t) } ?: false
            )
        }
        scheduleSave()
    }

    fun setFavorite(value: Boolean) = update { it.copy(favorite = value) }

    fun refreshFavorite() {
        val track = state.value.current ?: return
        setFavorite(library.isFavorite(track))
    }

    fun markHistory(track: Track) {
        library.recordPlay(track)
    }

    fun playIndex(index: Int, recordHistory: Boolean = false): Boolean {
        if (!queue.setIndex(index)) return false
        val track = queue.current() ?: return false
        setCurrent(track)
        if (recordHistory) markHistory(track)
        scheduleSave()
        return true
    }

    fun setTracks(tracks: List<Track>, startIndex: Int = 0) {
        queue.setTracks(tracks, startIndex)
        setCurrent(queue.current())
        scheduleSave()
    }

    fun appendToQueue(track: Track) {
        queue.append(track)
        scheduleSave()
    }

    fun extendQueue(tracks: List<Track>) {
        queue.extend(tracks)
        scheduleSave()
    }

    fun insertNext(track: Track) {
        queue.insertNext(track)
        scheduleSave()
    }

    fun removeAt(index: Int): Track? {
        val removed = queue.removeAt(index)
        if (removed != null) {
            setCurrent(queue.current())
            scheduleSave()
        }
        return removed
    }

    fun removeByUid(uid: String): Boolean {
        val index = queue.tracks().indexOfFirst { it.uid == uid }
        if (index < 0) return false
        removeAt(index)
        return true
    }

    fun moveQueueItem(src: Int, dst: Int): Boolean {
        val result = queue.move(src, dst)
        if (result) scheduleSave()
        return result
    }

    fun clearQueue() {
        queue.clear()
        setCurrent(null)
        sessionStore.clear()
        update { it.copy(queue = emptyList(), queueIndex = -1) }
    }

    fun setMode(mode: PlayMode) {
        queue.mode = mode
        config.setString("playback.mode", mode.configName)
        update { it.copy(mode = mode) }
        scheduleSave()
    }

    fun cycleMode() {
        val modes = PlayMode.entries
        val next = modes[(queue.mode.ordinal + 1) % modes.size]
        setMode(next)
    }

    fun toggleFavorite() {
        val track = state.value.current ?: return
        val added = library.toggleFavorite(track)
        setFavorite(added)
    }

    fun nextIndex(manual: Boolean = true, autoAdvance: Boolean = false): Int? =
        queue.nextIndex(manual = manual, autoAdvance = autoAdvance)

    fun previousIndex(manual: Boolean = true): Int? = queue.prevIndex(manual = manual)

    fun applyNext(manual: Boolean = true, autoAdvance: Boolean = false): Boolean {
        val next = queue.nextIndex(manual = manual, autoAdvance = autoAdvance) ?: return false
        return playIndex(next, recordHistory = false)
    }

    fun applyPrevious(): Boolean {
        val previous = queue.prevIndex(manual = true) ?: return false
        return playIndex(previous, recordHistory = false)
    }

    fun saveSession() {
        sessionStore.save(queue, state.value.positionMs)
    }

    fun scheduleSave() {
        saveJob?.cancel()
        saveJob = scope.launch {
            delay(1500)
            saveSession()
        }
    }

    fun restoreSession() {
        if (!config.getBoolean("playback.restore_session", true)) {
            sessionStore.clear()
            return
        }
        val session = sessionStore.load() ?: return
        queue.loadSnapshot(session.queue)
        val track = queue.current()
        val restorePosition = if (config.getBoolean("playback.remember_progress", true)) session.positionMs else 0L
        if (track != null) {
            update {
                it.copy(
                    current = track,
                    requested = track,
                    positionMs = restorePosition,
                    durationMs = track.interval * 1000L,
                    playing = false,
                    loading = false,
                    queue = queue.tracks(),
                    queueIndex = queue.index,
                    mode = queue.mode
                )
            }
        }
    }

    private fun publishQueue() {
        update {
            it.copy(
                queue = queue.tracks(),
                queueIndex = queue.index,
                favorite = it.current?.let { track -> library.isFavorite(track) } ?: false,
                mode = queue.mode
            )
        }
        scheduleSave()
    }

    private inline fun update(block: (PlaybackSnapshot) -> PlaybackSnapshot) {
        state.value = block(state.value)
    }
}
