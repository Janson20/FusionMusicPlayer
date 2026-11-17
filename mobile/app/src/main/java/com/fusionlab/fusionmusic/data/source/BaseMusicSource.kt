package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.QualityLevel
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.HttpEngine
import com.fusionlab.fusionmusic.data.net.parseJsonObject
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.util.Locale

abstract class BaseMusicSource(
    val sourceId: String,
    val sourceName: String,
    timeoutSeconds: Int = 15,
    proxy: String = "",
    val log: AppLog? = null
) {
    val http: HttpEngine = HttpEngine(timeoutSeconds, proxy, log)
    var lastSearchTotal: Int = 0
        private set

    open val searchLimit: Int = 30

    abstract fun search(keyword: String, page: Int = 1, limit: Int = 30): List<MusicInfo>

    abstract fun getMusicUrl(info: MusicInfo, quality: String = "128k"): String?

    abstract fun getLyric(info: MusicInfo): String?

    abstract fun getPicUrl(info: MusicInfo): String?

    open fun getBestQuality(info: MusicInfo, preferred: String = "128k"): String {
        val available = info.types.mapNotNull { item ->
            item["type"]?.jsonPrimitive?.content?.takeIf { it.isNotBlank() }
        }.toSet()
        if (available.isEmpty()) return QualityLevel.LOW
        if (available.contains(preferred)) return preferred
        for (quality in QualityLevel.ALL) {
            if (available.contains(quality)) return quality
        }
        return QualityLevel.LOW
    }

    open fun getDownloadHeaders(): Map<String, String> = emptyMap()

    open fun getDownloadCookies(): Map<String, String> = emptyMap()

    protected fun setSearchTotal(value: Any?) {
        val parsed = when (value) {
            is Number -> value.toInt()
            is String -> value.toIntOrNull() ?: 0
            null -> 0
            else -> value.toString().toIntOrNull() ?: 0
        }
        lastSearchTotal = parsed.coerceAtLeast(0)
    }

    protected fun formatSize(sizeBytes: Long): String {
        if (sizeBytes < 1024) return sizeBytes.toString() + "B"
        if (sizeBytes < 1024L * 1024L) {
            return String.format(Locale.US, "%.1fK", sizeBytes / 1024.0)
        }
        return String.format(Locale.US, "%.1fM", sizeBytes / (1024.0 * 1024.0))
    }

    protected fun getJson(
        url: String,
        query: Map<String, String> = emptyMap(),
        headers: Map<String, String> = emptyMap()
    ): JsonObject? {
        return parseJsonObject(http.getText(url, query, headers))
    }

    protected fun postFormJson(
        url: String,
        form: Map<String, String> = emptyMap(),
        headers: Map<String, String> = emptyMap()
    ): JsonObject? {
        return parseJsonObject(http.postFormText(url, form, headers))
    }

    protected fun text(
        url: String,
        query: Map<String, String> = emptyMap(),
        headers: Map<String, String> = emptyMap()
    ): String? = http.getText(url, query, headers)

    protected fun stringField(obj: JsonObject?, key: String, fallback: String = ""): String =
        obj?.string(key, fallback) ?: fallback
}
