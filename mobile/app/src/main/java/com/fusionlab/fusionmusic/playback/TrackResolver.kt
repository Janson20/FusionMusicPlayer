package com.fusionlab.fusionmusic.playback

import android.content.Context
import android.net.Uri
import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.QualityLevel
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.source.SourceRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

data class Resolved(
    val track: Track,
    val uri: Uri,
    val isLocal: Boolean,
    val quality: String,
    val fallback: Boolean = false,
    val requested: Track = track
)

class TrackResolver(
    private val context: Context,
    private val config: ConfigRepository,
    private val sources: SourceRegistry,
    private val cache: MediaCache,
    private val log: AppLog
) {
    suspend fun resolve(
        track: Track,
        quality: String = "320k",
        allowFallback: Boolean = true,
        cacheMedia: Boolean = false
    ): Resolved? = withContext(Dispatchers.IO) {
        if (track.isLocal || track.source == Track.LOCAL_SOURCE) {
            return@withContext resolveLocal(track)
        }

        val info = track.toMusicInfo()
        var url = ""
        var actualQuality = ""
        for (candidate in sources.qualityOrder(info, quality, track.source)) {
            val candidateUrl = sources.getMusicUrlExact(info, candidate, track.source)
            if (!candidateUrl.isNullOrBlank()) {
                url = candidateUrl
                actualQuality = candidate
                break
            }
        }

        if (url.isNotBlank()) {
            val headers = sources.downloadHeaders(track.source)
            val cookies = sources.downloadCookies(track.source)
            val needsCache = cacheMedia || headers.isNotEmpty() || cookies.isNotEmpty()
            if (needsCache) {
                val identity = track.source + ":" + track.songmid + ":" + actualQuality
                val cached = cache.download(
                    url = url,
                    headers = headers,
                    cookies = cookies,
                    identity = identity,
                    expectedSeconds = track.interval,
                    suffix = suffixFromUrl(url)
                )
                trimCache()
                if (cached != null) {
                    return@withContext Resolved(
                        track = track,
                        uri = Uri.fromFile(cached.file),
                        isLocal = true,
                        quality = actualQuality,
                        requested = track
                    )
                }
                if (headers.isNotEmpty() || cookies.isNotEmpty()) {
                    log.w("TrackResolver", "cached playback unavailable for " + track.name)
                }
            }
            if (headers.isEmpty() && cookies.isEmpty()) {
                return@withContext Resolved(
                    track = track,
                    uri = Uri.parse(url),
                    isLocal = false,
                    quality = actualQuality,
                    requested = track
                )
            }
        }

        if (!allowFallback) {
            log.w("TrackResolver", "no playable url: " + track.name)
            return@withContext null
        }
        val fallback = sources.resolveTrack(info, quality)
        if (fallback == null) {
            log.w("TrackResolver", "fallback failed: " + track.name)
            return@withContext null
        }
        val fallbackTrack = Track.fromMusicInfo(fallback.info)
        val headers = sources.downloadHeaders(fallback.info.source)
        val cookies = sources.downloadCookies(fallback.info.source)
        val identity = fallback.info.source + ":" + fallback.info.songmid + ":" + fallback.quality
        val cached = cache.download(
            url = fallback.url,
            headers = headers,
            cookies = cookies,
            identity = identity,
            expectedSeconds = fallbackTrack.interval,
            suffix = suffixFromUrl(fallback.url)
        )
        trimCache()
        if (cached != null) {
            Resolved(
                track = fallbackTrack,
                uri = Uri.fromFile(cached.file),
                isLocal = true,
                quality = fallback.quality,
                fallback = true,
                requested = track
            )
        } else if (headers.isEmpty() && cookies.isEmpty()) {
            Resolved(
                track = fallbackTrack,
                uri = Uri.parse(fallback.url),
                isLocal = false,
                quality = fallback.quality,
                fallback = true,
                requested = track
            )
        } else {
            null
        }
    }

    private fun resolveLocal(track: Track): Resolved? {
        val path = track.path
        if (path.isBlank()) return null
        val uri = if (path.startsWith("content://") || path.startsWith("file://")) {
            Uri.parse(path)
        } else {
            val file = File(path)
            if (!file.exists()) return null
            Uri.fromFile(file)
        }
        val quality = when (path.substringAfterLast('.', "").lowercase()) {
            "flac", "ape" -> QualityLevel.HIGH
            "wav", "aiff" -> "lossless"
            else -> QualityLevel.MEDIUM
        }
        return Resolved(track = track, uri = uri, isLocal = true, quality = quality, requested = track)
    }

    private fun trimCache() {
        val limitMb = config.getInt("storage.media_cache_limit_mb", 2048).coerceIn(128, 8192)
        cache.trim(limitMb.toLong() * 1024L * 1024L)
    }

    private fun suffixFromUrl(url: String): String {
        val withoutQuery = url.substringBefore('?')
        val raw = withoutQuery.substringAfterLast('.', "").lowercase()
        val allowed = setOf("mp3", "flac", "m4a", "aac", "wav", "ogg", "opus", "wma", "ape")
        return if (raw in allowed) "." + raw else ""
    }
}
