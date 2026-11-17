package com.fusionlab.fusionmusic.core.loudness

import com.fusionlab.fusionmusic.core.util.JsonFiles
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.io.File
import java.util.Locale

@Serializable
data class LoudnessEntry(
    @SerialName("lufs") val loudnessLufs: Double? = null,
    val peak: Double = 0.0,
    @SerialName("secs") val seconds: Double = 0.0,
    val partial: Boolean = true,
    val source: String = "",
    val method: String = "decode",
    val ok: Boolean = true,
    val at: Double = 0.0
) {
    fun gainDb(
        targetLufs: Double,
        preampDb: Double,
        allowBoost: Boolean,
        maxGainDb: Double,
        minGainDb: Double
    ): Double {
        if (!ok) return 0.0
        val ceiling = if (partial) LoudnessConstants.PARTIAL_PEAK_CEILING else LoudnessConstants.DEFAULT_PEAK_CEILING
        return LoudnessGain.gainDb(
            loudnessLufs = loudnessLufs,
            peak = peak,
            targetLufs = targetLufs,
            preampDb = preampDb,
            allowBoost = allowBoost,
            peakCeiling = ceiling,
            maxGainDb = maxGainDb,
            minGainDb = minGainDb
        )
    }
}

@Serializable
private data class LoudnessFile(
    val version: Int = 2,
    val analysis: Int = LoudnessConstants.ANALYSIS_VERSION,
    val entries: Map<String, LoudnessEntry> = emptyMap()
)

data class LoudnessStats(
    val total: Int = 0,
    val measured: Int = 0,
    val failed: Int = 0,
    val bytes: Long = 0L,
    val avgLoudness: Double? = null,
    val pending: Int = 0,
    val analyzing: String = "",
    val enabled: Boolean = true
)

class LoudnessStore(context: android.content.Context) {
    private val file = File(File(context.filesDir, "data").apply { mkdirs() }, "loudness.json")
    private val lock = Any()
    private val saveLock = Any()
    private val entries = HashMap<String, LoudnessEntry>()

    init {
        load()
    }

    fun get(uid: String, retryFailed: Boolean = true): LoudnessEntry? {
        val key = uid.trim()
        if (key.isEmpty()) return null
        synchronized(lock) {
            val item = entries[key] ?: return null
            if (!item.ok && retryFailed && failureExpired(item)) return null
            return item
        }
    }

    fun put(uid: String, entry: LoudnessEntry) {
        if (uid.isBlank()) return
        synchronized(lock) {
            entries[uid] = entry
            pruneLocked()
        }
        save()
    }

    fun clear(): Int {
        val count = synchronized(lock) {
            val n = entries.size
            entries.clear()
            n
        }
        save()
        return count
    }

    fun size(): Int = synchronized(lock) { entries.size }

    fun measuredCount(): Int = synchronized(lock) { entries.values.count { it.ok } }

    fun sourceOffsetDb(source: String, options: GainOptions): Double {
        val key = source.trim()
        if (key.isEmpty()) return 0.0
        val values = synchronized(lock) {
            entries.values.filter { it.ok && it.source == key && it.loudnessLufs != null }
                .map { it.gainDb(options.targetLufs, options.preampDb, options.allowBoost, options.maxGainDb, options.minGainDb) }
        }
        if (values.size < MIN_SOURCE_SAMPLES) return 0.0
        val sorted = values.sorted()
        val mid = sorted.size / 2
        val median = if (sorted.size % 2 == 0) (sorted[mid - 1] + sorted[mid]) / 2.0 else sorted[mid]
        return median.coerceIn(-SOURCE_OFFSET_LIMIT_DB, SOURCE_OFFSET_LIMIT_DB)
    }

    fun countForSource(source: String): Int = synchronized(lock) {
        entries.values.count { it.ok && it.source == source }
    }

    fun stats(enabled: Boolean, pending: Int, analyzing: String): LoudnessStats {
        val values = synchronized(lock) { entries.values.toList() }
        val measured = values.filter { it.ok }
        val loudness = measured.mapNotNull { it.loudnessLufs }
        return LoudnessStats(
            total = values.size,
            measured = measured.size,
            failed = values.size - measured.size,
            bytes = if (file.exists()) file.length() else 0L,
            avgLoudness = if (loudness.isEmpty()) null else loudness.average(),
            pending = pending,
            analyzing = analyzing,
            enabled = enabled
        )
    }

    private fun load() {
        try {
            if (!file.exists()) return
            val data = JsonFiles.pretty.decodeFromString(LoudnessFile.serializer(), file.readText(Charsets.UTF_8))
            if (data.version != CACHE_VERSION || data.analysis != LoudnessConstants.ANALYSIS_VERSION) {
                file.delete()
                return
            }
            synchronized(lock) {
                entries.clear()
                entries.putAll(data.entries)
            }
        } catch (_: Exception) {
            JsonFiles.backupCorrupt(file)
        }
    }

    private fun save() {
        val snapshot = synchronized(lock) {
            LoudnessFile(version = CACHE_VERSION, analysis = LoudnessConstants.ANALYSIS_VERSION, entries = HashMap(entries))
        }
        synchronized(saveLock) {
            try {
                JsonFiles.writeTextAtomic(file, JsonFiles.compact.encodeToString(LoudnessFile.serializer(), snapshot))
            } catch (_: Exception) {
                // 缓存写失败不能影响播放，下次测量会再次尝试。
            }
        }
    }

    private fun failureExpired(item: LoudnessEntry): Boolean {
        return System.currentTimeMillis() / 1000.0 - item.at > FAILURE_TTL_SECONDS
    }

    private fun pruneLocked() {
        if (entries.size <= MAX_ENTRIES) return
        val ordered = entries.entries.sortedBy { it.value.at }
        val remove = entries.size - MAX_ENTRIES
        for (index in 0 until remove) entries.remove(ordered[index].key)
    }

    data class GainOptions(
        val targetLufs: Double = LoudnessConstants.DEFAULT_TARGET_LUFS,
        val preampDb: Double = 0.0,
        val allowBoost: Boolean = true,
        val maxGainDb: Double = LoudnessConstants.DEFAULT_MAX_GAIN_DB,
        val minGainDb: Double = LoudnessConstants.DEFAULT_MIN_GAIN_DB
    )

    companion object {
        const val CACHE_VERSION = 2
        const val FAILURE_TTL_SECONDS = 24.0 * 3600.0
        const val MAX_ENTRIES = 20000
        const val MIN_SOURCE_SAMPLES = 5
        const val SOURCE_OFFSET_LIMIT_DB = 6.0

        fun describe(entry: LoudnessEntry, gain: Double): String {
            val method = when (entry.method) {
                "tag" -> "标签"
                "offset" -> "音源估计"
                else -> "实测"
            }
            val span = if (entry.partial) "前 " + String.format(Locale.US, "%.0f", entry.seconds) + " 秒" else "全曲"
            val loudness = entry.loudnessLufs?.let { String.format(Locale.US, "%.1f", it) + " LUFS" } ?: "未测出"
            return LoudnessGain.describe(gain) + "（" + method + " · " + loudness + " · " + span + "）"
        }
    }
}
