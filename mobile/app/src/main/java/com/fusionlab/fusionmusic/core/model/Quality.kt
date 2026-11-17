package com.fusionlab.fusionmusic.core.model

import java.util.Locale

object QualityLevel {
    const val LOW = "128k"
    const val MEDIUM = "320k"
    const val HIGH = "flac"
    const val LOSSLESS = "flac24bit"
    val ALL = listOf("flac24bit", "flac", "320k", "128k")
    const val AUTO = "auto"

    fun index(quality: String): Int {
        val index = ALL.indexOf(quality)
        return if (index < 0) 3 else index
    }
}

val QUALITY_SHORT_LABELS: Map<String, String> = mapOf(
    "flac24bit" to "Hi-Res",
    "flac" to "无损",
    "320k" to "320K",
    "128k" to "标准",
    "lossless" to "无损",
    "auto" to "自动"
)

val QUALITY_LABELS: Map<String, String> = mapOf(
    "flac24bit" to "Hi-Res 母带",
    "flac" to "无损 FLAC",
    "320k" to "高品质 320K",
    "128k" to "标准 128K"
)

val QUALITY_BITRATES: Map<String, Int> = mapOf(
    "flac24bit" to 2300,
    "flac" to 900,
    "320k" to 320,
    "128k" to 128
)

fun qualityShort(quality: String): String {
    val key = quality.trim().lowercase(Locale.ROOT)
    return QUALITY_SHORT_LABELS[key] ?: key
}

fun qualityLabel(quality: String): String {
    val key = quality.trim().lowercase(Locale.ROOT)
    return QUALITY_LABELS[key] ?: quality
}

fun qualityLadder(requested: String): List<String> {
    val value = requested.trim().lowercase(Locale.ROOT)
    if (value == QualityLevel.AUTO || !QualityLevel.ALL.contains(value)) {
        return QualityLevel.ALL.toList()
    }
    return QualityLevel.ALL.drop(QualityLevel.ALL.indexOf(value))
}

fun formatDuration(seconds: Int): String {
    if (seconds <= 0) return "0:00"
    if (seconds >= 3600) {
        val hours = seconds / 3600
        val minutes = (seconds % 3600) / 60
        val secs = seconds % 60
        return hours.toString() + ":" + minutes.toString().padStart(2, '0') + ":" + secs.toString().padStart(2, '0')
    }
    val minutes = seconds / 60
    val secs = seconds % 60
    return minutes.toString() + ":" + secs.toString().padStart(2, '0')
}

fun normalizeSingers(raw: String): String {
    if (raw.isEmpty()) return ""
    return raw.replace("&", "、").replace(";", "、").replace("/", "、")
}
