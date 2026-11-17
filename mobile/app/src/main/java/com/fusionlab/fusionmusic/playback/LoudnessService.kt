package com.fusionlab.fusionmusic.playback

import com.fusionlab.fusionmusic.core.loudness.AnalysisInput
import com.fusionlab.fusionmusic.core.loudness.LoudnessAnalyzer
import com.fusionlab.fusionmusic.core.loudness.LoudnessEntry
import com.fusionlab.fusionmusic.core.loudness.LoudnessGain
import com.fusionlab.fusionmusic.core.loudness.LoudnessStats
import com.fusionlab.fusionmusic.core.loudness.LoudnessStore
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.source.SourceRegistry
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * 音量均衡的后台队列。同一时间只解码一首；切歌时取消上一首的测量，
 * 保证解码器、带宽与 CPU 不会被已经过期的任务占住。
 */
class LoudnessService(
    context: android.content.Context,
    private val config: ConfigRepository,
    private val sources: SourceRegistry,
    private val log: AppLog,
    private val scope: CoroutineScope
) {
    private val analyzer = LoudnessAnalyzer(context.applicationContext, log)
    private val store = LoudnessStore(context.applicationContext)
    private val mutex = Mutex()
    private val jobs = LinkedHashMap<String, Job>()
    private val revision = MutableStateFlow(0L)
    @Volatile private var activeUid = ""

    val revisions: StateFlow<Long> = revision

    val enabled: Boolean get() = config.getBoolean("audio.equalize", true)

    fun gainFor(track: Track?): Double {
        if (track == null || !enabled) return 0.0
        val uid = track.uid
        val entry = store.get(uid, retryFailed = false)
        if (entry != null && entry.ok) {
            return entry.gainDb(
                options.targetLufs,
                options.preampDb,
                options.allowBoost,
                options.maxGainDb,
                options.minGainDb
            )
        }
        if (config.getBoolean("audio.source_offset", true)) {
            return store.sourceOffsetDb(track.source, options)
        }
        return 0.0
    }

    fun describe(track: Track?): String {
        if (track == null || !enabled) return ""
        val entry = store.get(track.uid, retryFailed = false)
        if (entry != null && entry.ok) {
            return LoudnessStore.describe(
                entry,
                entry.gainDb(options.targetLufs, options.preampDb, options.allowBoost, options.maxGainDb, options.minGainDb)
            )
        }
        if (config.getBoolean("audio.source_offset", true)) {
            val offset = store.sourceOffsetDb(track.source, options)
            if (offset != 0.0) return LoudnessGain.describe(offset) + "（音源估计）"
        }
        return ""
    }

    fun stats(): LoudnessStats {
        val running = activeUid.isNotBlank()
        val pending = synchronized(jobs) { (jobs.size - if (running) 1 else 0).coerceAtLeast(0) }
        return store.stats(enabled, pending, activeUid)
    }

    fun request(track: Track, target: String, local: Boolean = false, focus: Boolean = true): Boolean {
        if (!enabled || track.uid.isBlank()) return false
        if (store.get(track.uid) != null) return false
        val existing = synchronized(jobs) { jobs[track.uid] }
        if (existing != null) {
            if (focus) focus(track.uid)
            return false
        }
        if (focus) focus(track.uid)
        val job = scope.launch(Dispatchers.IO, start = CoroutineStart.LAZY) {
            process(track, target, local)
        }
        synchronized(jobs) { jobs[track.uid] = job }
        job.invokeOnCompletion {
            synchronized(jobs) { jobs.remove(track.uid) }
        }
        job.start()
        return true
    }

    fun prefetch(track: Track?, target: String, local: Boolean = false): Boolean {
        if (track == null || !config.getBoolean("audio.prefetch_next", true)) return false
        return request(track, target, local, focus = false)
    }

    fun clear() {
        store.clear()
        synchronized(jobs) { jobs.values.toList() }.forEach { it.cancel() }
        revision.value++
    }

    fun clearFailed() {
        // 没有单独的 failed 清理 API；以“清空整个缓存”作为用户可预期的动作。
        clear()
    }

    private fun focus(uid: String) {
        synchronized(jobs) {
            val others = jobs.filterKeys { it != uid }.values.toList()
            others.forEach { it.cancel() }
        }
    }

    private suspend fun process(track: Track, target: String, local: Boolean) {
        try {
            mutex.withLock {
                activeUid = track.uid
                val input = if (target.isBlank()) {
                    null
                } else {
                    AnalysisInput(
                        location = target,
                        headers = if (local) emptyMap() else sources.downloadHeaders(track.source),
                        cookies = if (local) emptyMap() else sources.downloadCookies(track.source),
                        local = local
                    )
                }
                val decoded = if (input == null) null else analyzer.analyze(
                    input = input,
                    maxSeconds = config.getInt("audio.analysis_seconds", 0).coerceAtLeast(0),
                    timeoutSeconds = config.getInt("audio.decode_timeout", 180).coerceIn(10, 600)
                )
                val entry = if (decoded != null && decoded.result.measurable) {
                    LoudnessEntry(
                        loudnessLufs = decoded.result.loudnessLufs,
                        peak = decoded.result.peak,
                        seconds = decoded.result.analyzedSeconds,
                        partial = !decoded.complete || config.getInt("audio.analysis_seconds", 0) > 0,
                        source = track.source,
                        method = "decode",
                        ok = true,
                        at = System.currentTimeMillis() / 1000.0
                    )
                } else {
                    LoudnessEntry(
                        loudnessLufs = null,
                        peak = 0.0,
                        seconds = 0.0,
                        partial = true,
                        source = track.source,
                        method = "decode",
                        ok = false,
                        at = System.currentTimeMillis() / 1000.0
                    )
                }
                store.put(track.uid, entry)
                revision.value++
                if (entry.ok) {
                    log.i("Loudness", track.uid + " " + LoudnessStore.describe(entry, gainFor(track)))
                } else {
                    log.w("Loudness", track.uid + " 无法测量响度")
                }
            }
        } catch (_: CancellationException) {
            // 用户切歌，任务作废。
        } catch (error: Exception) {
            log.w("Loudness", "analyze failed: " + error.message)
        } finally {
            if (activeUid == track.uid) activeUid = ""
        }
    }

    private val options: LoudnessStore.GainOptions
        get() = LoudnessStore.GainOptions(
            targetLufs = config.getDouble("audio.target_lufs", -14.0),
            preampDb = config.getDouble("audio.preamp_db", 0.0),
            allowBoost = config.getBoolean("audio.allow_boost", true),
            maxGainDb = config.getDouble("audio.max_gain_db", 12.0),
            minGainDb = config.getDouble("audio.min_gain_db", -24.0)
        )
}
