package com.fusionlab.fusionmusic.data.local

import android.content.Context
import android.content.Intent
import android.media.MediaMetadataRetriever
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import com.fusionlab.fusionmusic.core.model.SourceRegistryMeta
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.model.durationMatches
import com.fusionlab.fusionmusic.core.model.normalizeSingers
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import com.fusionlab.fusionmusic.data.source.SourceRegistry
import com.fusionlab.fusionmusic.data.store.LibraryStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

data class LocalScanState(
    val scanning: Boolean = false,
    val phase: String = "",
    val current: Int = 0,
    val total: Int = 0,
    val message: String = ""
)

class LocalRepository(
    private val context: Context,
    private val config: ConfigRepository,
    private val library: LibraryStore,
    private val sources: SourceRegistry,
    private val log: AppLog,
    private val scope: CoroutineScope
) {
    private val dataDir = File(context.filesDir, "data").apply { mkdirs() }
    private val coverDir = File(dataDir, "cache/cover").apply { mkdirs() }
    private val scanState = MutableStateFlow(LocalScanState())
    private val trackState = MutableStateFlow(library.localTracks())
    private var scanJob: Job? = null

    val state: StateFlow<LocalScanState> = scanState
    val tracks: StateFlow<List<Track>> = trackState

    fun refreshTracks() {
        trackState.value = library.localTracks()
    }

    fun folders(): List<String> = config.getStringList("local.folders")

    fun addFolder(uri: Uri): Boolean {
        return try {
            context.contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION
            )
            val current = folders().toMutableList()
            if (!current.contains(uri.toString())) current.add(uri.toString())
            config.setStringList("local.folders", current)
            true
        } catch (error: Exception) {
            log.w("Local", "add folder failed: " + error.message)
            false
        }
    }

    fun removeFolder(uri: String) {
        val current = folders().toMutableList()
        current.remove(uri)
        config.setStringList("local.folders", current)
        try {
            context.contentResolver.releasePersistableUriPermission(Uri.parse(uri), Intent.FLAG_GRANT_READ_URI_PERMISSION)
        } catch (_: Exception) {
            // permission may already be gone
        }
    }

    fun scan() {
        if (scanState.value.scanning) return
        scanJob?.cancel()
        scanJob = scope.launch {
            scanState.value = LocalScanState(scanning = true, phase = "扫描文件", message = "正在读取本地音乐…")
            val previous = library.localTracks().associateBy { it.path }
            val documents = mutableListOf<Pair<DocumentFile, Uri>>()
            for (folder in folders()) {
                try {
                    val tree = DocumentFile.fromTreeUri(context, Uri.parse(folder)) ?: continue
                    collectFiles(tree, documents)
                } catch (error: Exception) {
                    log.w("Local", "scan folder failed: " + folder + " / " + error.message)
                }
            }
            val total = documents.size
            val tracks = mutableListOf<Track>()
            scanState.value = scanState.value.copy(total = total, current = 0)
            for ((index, item) in documents.withIndex()) {
                if (!isActive) return@launch
                val (document, uri) = item
                val track = try {
                    readTrack(document, uri, previous[uri.toString()])
                } catch (error: Exception) {
                    log.w("Local", "read track failed: " + error.message)
                    null
                }
                if (track != null) tracks.add(track)
                scanState.value = scanState.value.copy(current = index + 1)
            }

            if (config.getBoolean("local.match_online", true) && tracks.isNotEmpty()) {
                scanState.value = scanState.value.copy(phase = "匹配封面与歌词", current = 0, total = tracks.size)
                val source = sources.getSource("wy") as? NeteaseSource
                if (source != null) {
                    val semaphore = Semaphore(4)
                    val matched = coroutineScope {
                        tracks.mapIndexed { index, track ->
                            async(Dispatchers.IO) {
                                semaphore.withPermit {
                                    if (needsMatch(track)) matchTrack(source, track)
                                }
                                scanState.value = scanState.value.copy(current = index + 1)
                            }
                        }.awaitAll()
                    }
                    // results are mutated in place; no extra work needed
                }
            }

            library.setLocalTracks(tracks)
            trackState.value = tracks
            scanState.value = LocalScanState(
                scanning = false,
                message = "扫描完成：" + tracks.size + " 首"
            )
        }
    }

    fun cancel() {
        scanJob?.cancel()
        scanState.value = LocalScanState(scanning = false, message = "已取消扫描")
    }

    private fun collectFiles(dir: DocumentFile, out: MutableList<Pair<DocumentFile, Uri>>) {
        val children = try {
            dir.listFiles()
        } catch (_: Exception) {
            emptyArray()
        }
        for (child in children) {
            if (child.isDirectory) {
                collectFiles(child, out)
            } else if (isAudioName(child.name ?: "")) {
                out.add(child to child.uri)
            }
        }
    }

    private fun isAudioName(name: String): Boolean {
        val extensions = config.getStringList("local.extensions").ifEmpty {
            listOf(".mp3", ".flac", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".wma")
        }
        val lower = name.lowercase()
        return extensions.any { lower.endsWith(it) }
    }

    private fun readTrack(document: DocumentFile, uri: Uri, previous: Track?): Track? {
        val name = document.name ?: return null
        val retriever = MediaMetadataRetriever()
        var title = name.substringBeforeLast('.')
        var artist = ""
        var album = ""
        var duration = 0
        var embedded: ByteArray? = null
        try {
            retriever.setDataSource(context, uri)
            title = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_TITLE)?.trim().orEmpty().ifBlank { title }
            artist = normalizeSingers(retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ARTIST)?.trim().orEmpty())
            album = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_ALBUM)?.trim().orEmpty()
            val rawDuration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            duration = if (rawDuration > 0) (rawDuration / 1000).toInt() else 0
            embedded = retriever.embeddedPicture
        } catch (error: Exception) {
            log.d("Local", "metadata failed: " + error.message)
        } finally {
            try {
                retriever.release()
            } catch (_: Exception) {
                // ignore
            }
        }
        var cover = ""
        if (embedded != null && embedded.isNotEmpty()) {
            cover = saveCover(embedded)
        }
        val result = Track(
            source = Track.LOCAL_SOURCE,
            songmid = uri.toString(),
            name = title,
            singer = artist,
            album = album,
            interval = duration,
            cover = cover,
            path = uri.toString(),
            addedAt = previous?.addedAt ?: (System.currentTimeMillis() / 1000L)
        )
        if (previous != null && previous.interval == duration && previous.matchSongmid.isNotBlank()) {
            result.reason = ""
            result.matchSource = previous.matchSource
            result.matchSongmid = previous.matchSongmid
            if (cover.isBlank()) result.cover = previous.cover
        }
        return result
    }

    private fun needsMatch(track: Track): Boolean {
        if (track.name.isBlank()) return false
        if (track.cover.isBlank()) return true
        return track.matchSongmid.isBlank()
    }

    private fun matchTrack(source: NeteaseSource, track: Track) {
        try {
            val keyword = (track.name + " " + track.singer).trim()
            val results = source.search(keyword, page = 1, limit = 10)
            val candidate = results.firstOrNull { info ->
                durationMatches(info, track.interval) &&
                    (info.name.equals(track.name, ignoreCase = true) ||
                        info.name.contains(track.name) || track.name.contains(info.name))
            } ?: return
            track.matchSource = candidate.source
            track.matchSongmid = candidate.songmid
            if (track.cover.isBlank() && !candidate.img.isNullOrBlank()) {
                track.cover = candidate.img
            }
        } catch (error: Exception) {
            log.d("Local", "match failed: " + track.name + " / " + error.message)
        }
    }

    private fun saveCover(bytes: ByteArray): String {
        return try {
            val key = Crypto.sha256Bytes(bytes).joinToString("") { "%02x".format(it.toInt() and 0xFF) }.take(32)
            val file = File(coverDir, key + ".img")
            if (!file.exists()) {
                FileOutputStream(file).use { stream ->
                    stream.write(bytes)
                    stream.fd.sync()
                }
            }
            Uri.fromFile(file).toString()
        } catch (_: Exception) {
            ""
        }
    }
}
