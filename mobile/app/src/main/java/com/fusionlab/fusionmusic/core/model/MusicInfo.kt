package com.fusionlab.fusionmusic.core.model

import kotlinx.serialization.json.JsonObject

data class MusicInfo(
    val name: String,
    val singer: String,
    val source: String,
    val songmid: String,
    val albumName: String = "",
    val albumId: String = "",
    val interval: Int = 0,
    val img: String? = null,
    val lrc: String? = null,
    val types: List<JsonObject> = emptyList(),
    val typeDetail: Map<String, JsonObject> = emptyMap(),
    val otherSource: String? = null,
    val publishTime: Long = 0L,
    var isOriginal: Boolean = false,
    val originSongId: String = "",
    val originArtists: List<String> = emptyList(),
    val fee: Int = 0,
    var originalName: String = "",
    val playCount: Long = 0L
) {
    fun qualityList(): List<String> = types.mapNotNull { item ->
        item["type"]?.toString()?.trim('"')?.takeIf { it.isNotBlank() }
    }

    fun bestQuality(): String {
        for (quality in QualityLevel.ALL) {
            if (qualityList().contains(quality)) return quality
        }
        return QualityLevel.LOW
    }
}

fun durationMatches(info: MusicInfo, targetSeconds: Int, tolerance: Int = 15): Boolean {
    if (targetSeconds <= 0 || info.interval <= 0) return true
    return kotlin.math.abs(info.interval - targetSeconds) <= tolerance
}
