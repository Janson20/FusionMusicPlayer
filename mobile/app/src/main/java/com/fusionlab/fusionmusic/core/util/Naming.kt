package com.fusionlab.fusionmusic.core.util

import com.fusionlab.fusionmusic.core.model.Track

object Naming {
    private val ILLEGAL = Regex("[<>:\"/\\|?*\u0000-\u001f]")
    private val WHITESPACE = Regex("\\s+")
    private val PLACEHOLDER = Regex("\\{(\\w+)\\}")
    private val RESERVED = setOf(
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"
    )
    private const val MAX_STEM = 120
    private const val EDGE = " \t-—–_·.,"

    fun sanitizeFilename(raw: String, fallback: String = "未命名"): String {
        var text = ILLEGAL.replace(raw, "_")
        text = WHITESPACE.replace(text, " ").trim()
        text = text.trimEnd('.', ' ')
        if (text.isEmpty()) text = fallback
        if (RESERVED.contains(text.substringBefore('.').lowercase())) text = "_" + text
        if (text.length > MAX_STEM) text = text.take(MAX_STEM).trimEnd('.', ' ')
        return text.ifEmpty { fallback }
    }

    fun formatFilename(template: String, values: Map<String, String>, fallback: String = "未命名"): String {
        val pattern = template.ifBlank { "{name}" }
        var text = PLACEHOLDER.replace(pattern) { match ->
            values[match.groupValues[1]] ?: ""
        }
        text = WHITESPACE.replace(text, " ").trim()
        text = text.trim { EDGE.contains(it) }
        return sanitizeFilename(text, fallback)
    }

    fun trackValues(track: Track, index: Int = 0): Map<String, String> = mapOf(
        "name" to track.name.trim(),
        "singer" to track.singer.trim(),
        "album" to track.album.trim(),
        "source" to track.sourceText,
        "index" to if (index > 0) index.toString() else ""
    )

    fun suggestedStem(track: Track, template: String = "{singer} - {name}", index: Int = 0): String {
        val values = trackValues(track, index)
        val fallback = track.name.ifBlank { track.singer.ifBlank { "未命名" } }
        return formatFilename(template, values, fallback)
    }

    fun audioMime(suffix: String): String = when (suffix.lowercase()) {
        ".flac" -> "audio/flac"
        ".m4a", ".mp4", ".aac" -> "audio/mp4"
        ".ogg", ".opus" -> "audio/ogg"
        ".wav" -> "audio/wav"
        ".wma" -> "audio/x-ms-wma"
        else -> "audio/mpeg"
    }
}
