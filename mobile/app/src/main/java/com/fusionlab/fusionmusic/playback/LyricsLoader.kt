package com.fusionlab.fusionmusic.playback

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.core.util.JsonFiles
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.lyrics.Lyrics
import com.fusionlab.fusionmusic.data.net.Crypto
import com.fusionlab.fusionmusic.data.source.NeteaseExtras
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import com.fusionlab.fusionmusic.data.source.SourceRegistry
import kotlinx.serialization.Serializable
import java.io.File

@Serializable
private data class LyricCache(
    val lrc: String = "",
    val translation: String = "",
    val roma: String = "",
    val word: String = "",
    val wordTranslation: String = "",
    val wordRoma: String = "",
    val at: Long = 0L
)

class LyricsLoader(
    private val context: Context,
    private val config: ConfigRepository,
    private val sources: SourceRegistry,
    private val log: AppLog
) {
    private val cacheDir = File(context.filesDir, "data/cache/lyric").apply { mkdirs() }
    private val neteaseExtras: NeteaseExtras?
        get() = (sources.getSource("wy") as? NeteaseSource)?.let { NeteaseExtras(it) }

    fun load(track: Track): Lyrics {
        val showTranslation = config.getBoolean("lyrics.show_translation", true)
        val showRoma = config.getBoolean("lyrics.show_romaji", false)
        val dynamic = config.getBoolean("lyrics.dynamic", true)

        if (track.isLocal) {
            val sidecar = readLocalSidecar(track.path)
            if (sidecar.isNotBlank()) return build(sidecar, "", "", "", dynamic)
        }

        val sourceId = if (track.isLocal) track.matchSource else track.source
        val songId = if (track.isLocal) track.matchSongmid else track.songmid
        if (sourceId.isBlank() || songId.isBlank()) return Lyrics()

        val cacheEnabled = config.getBoolean("storage.cache_lyric", true)
        val cacheFile = cacheFile(sourceId, songId)
        if (cacheEnabled && cacheFile.exists()) {
            val cached = JsonFiles.read(cacheFile, LyricCache(), JsonFiles.pretty)
            if (cached.lrc.isNotBlank() || cached.word.isNotBlank()) {
                return build(
                    raw = cached.lrc,
                    translation = if (showTranslation) cached.translation else "",
                    roma = if (showRoma) cached.roma else "",
                    word = if (dynamic) cached.word else "",
                    dynamic = dynamic
                )
            }
        }

        var raw = ""
        var translation = ""
        var roma = ""
        var word = ""
        try {
            if (sourceId == "wy") {
                val bundle = neteaseExtras?.fetchLyricBundle(songId, showTranslation, showRoma, dynamic)
                if (bundle != null) {
                    raw = bundle.lrc
                    translation = bundle.translation
                    roma = bundle.roma
                    word = bundle.word
                }
            }
            if (raw.isBlank() && songId.isNotBlank()) {
                val info = track.toMusicInfo().copy(source = sourceId, songmid = songId)
                raw = sources.getLyric(info, sourceId) ?: ""
            }
        } catch (error: Exception) {
            log.w("LyricsLoader", "lyric fetch failed: " + error.message)
        }

        if (raw.isBlank() && word.isBlank()) return Lyrics()
        if (cacheEnabled && (raw.isNotBlank() || word.isNotBlank())) {
            try {
                JsonFiles.writeAtomic(
                    cacheFile,
                    LyricCache(
                        lrc = raw,
                        translation = translation,
                        roma = roma,
                        word = word,
                        at = System.currentTimeMillis()
                    ),
                    JsonFiles.compact
                )
            } catch (_: Exception) {
                // 缓存失败不影响本次歌词显示。
            }
        }
        return build(raw, translation, roma, word, dynamic)
    }

    private fun build(raw: String, translation: String, roma: String, word: String, dynamic: Boolean): Lyrics {
        val lyrics = Lyrics()
        if (raw.isNotBlank()) lyrics.parse(raw)
        if (lyrics.lines.isEmpty() && raw.isNotBlank()) return lyrics
        if (translation.isNotBlank()) lyrics.setTranslation(translation)
        if (roma.isNotBlank()) lyrics.setRoma(roma)
        if (dynamic) {
            if (word.isNotBlank()) lyrics.setWords(word)
            lyrics.applyPseudo()
        }
        return lyrics
    }

    private fun cacheFile(sourceId: String, songId: String): File {
        val key = Crypto.sha256Bytes((sourceId + ":" + songId).toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xFF) }
        return File(cacheDir, key + ".json")
    }

    private fun readLocalSidecar(path: String): String {
        if (path.isBlank()) return ""
        return try {
            if (path.startsWith("content://")) {
                val doc = DocumentFile.fromSingleUri(context, Uri.parse(path)) ?: return ""
                val name = doc.name ?: return ""
                val parent = doc.parentFile ?: return ""
                val stem = name.substringBeforeLast('.', name)
                val lrc = parent.findFile(stem + ".lrc") ?: return ""
                context.contentResolver.openInputStream(lrc.uri)?.bufferedReader(Charsets.UTF_8)?.use {
                    it.readText().take(MAX_LYRIC_CHARS)
                } ?: ""
            } else {
                val file = if (path.startsWith("file://")) {
                    File(Uri.parse(path).path ?: return "")
                } else {
                    File(path)
                }
                val stem = file.name.substringBeforeLast('.', file.name)
                val lrc = File(file.parentFile, stem + ".lrc")
                if (!lrc.exists()) "" else lrc.readText(Charsets.UTF_8).take(MAX_LYRIC_CHARS)
            }
        } catch (_: Exception) {
            ""
        }
    }

    companion object {
        private const val MAX_LYRIC_CHARS = 512 * 1024
    }
}
