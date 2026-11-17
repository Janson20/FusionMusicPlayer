package com.fusionlab.fusionmusic.data.store

import android.content.Context
import com.fusionlab.fusionmusic.core.model.PlayQueue
import com.fusionlab.fusionmusic.core.model.Session
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.util.JsonFiles
import java.io.File

class SessionStore(context: Context) {
    private val dataDir = File(context.filesDir, "data").apply { mkdirs() }
    private val file = File(dataDir, "session.json")
    private val lock = Any()

    fun load(): Session? = synchronized(lock) {
        val session = JsonFiles.read(file, Session(), JsonFiles.pretty)
        if (session.version != Session.SCHEMA_VERSION) return null
        val tracks = session.queue.tracks.filter { isPlayable(it) }
        if (tracks.isEmpty()) return null
        val index = session.queue.index.coerceIn(0, tracks.size - 1)
        session.copy(
            positionMs = session.positionMs.coerceAtLeast(0L),
            queue = session.queue.copy(tracks = tracks, index = index)
        )
    }

    fun save(queue: PlayQueue, positionMs: Long): Boolean = synchronized(lock) {
        val snapshot = queue.toSnapshot()
        if (snapshot.tracks.isEmpty()) {
            clear()
            return true
        }
        return try {
            JsonFiles.writeAtomic(
                file,
                Session(
                    version = Session.SCHEMA_VERSION,
                    savedAt = System.currentTimeMillis() / 1000L,
                    positionMs = positionMs.coerceAtLeast(0L),
                    queue = snapshot
                )
            )
            true
        } catch (_: Exception) {
            false
        }
    }

    fun clear() = synchronized(lock) {
        file.delete()
    }

    private fun isPlayable(track: Track): Boolean =
        track.name.isNotBlank() && (track.songmid.isNotBlank() || track.path.isNotBlank())
}
