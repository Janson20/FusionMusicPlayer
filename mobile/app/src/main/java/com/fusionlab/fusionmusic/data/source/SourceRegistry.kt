package com.fusionlab.fusionmusic.data.source

import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.QualityLevel
import com.fusionlab.fusionmusic.core.model.SourceRegistryMeta
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.model.durationMatches
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import java.util.concurrent.ConcurrentHashMap

data class SearchGroup(
    val source: String,
    val results: List<MusicInfo>,
    val total: Int
)

data class FallbackResult(
    val info: MusicInfo,
    val url: String,
    val quality: String
)

class SourceRegistry(
    private val config: ConfigRepository,
    private val log: AppLog
) {
    private val instances = ConcurrentHashMap<String, BaseMusicSource>()

    fun getSource(sourceId: String): BaseMusicSource? {
        val existing = instances[sourceId]
        if (existing != null) return existing
        val timeout = config.getInt("advanced.timeout", 15).coerceIn(5, 60)
        val proxy = config.getString("advanced.proxy", "")
        val created = when (sourceId) {
            "wy" -> NeteaseSource(timeout, proxy, log)
            "tx" -> QQMusicSource(timeout, proxy, log)
            "kw" -> KuwoMusicSource(timeout, proxy, log)
            "kg" -> KugouMusicSource(timeout, proxy, log)
            "mg" -> MiguMusicSource(timeout, proxy, log)
            "bili" -> BilibiliMusicSource(timeout, proxy, log)
            else -> null
        } ?: return null
        val raced = instances.putIfAbsent(sourceId, created)
        return raced ?: created
    }

    fun enabledSourceIds(): List<String> {
        val raw = config.getStringList("sources.enabled")
        val enabled = SourceRegistryMeta.normalizeLegacyEnabled(raw).toSet()
        return priorityIds().filter { enabled.contains(it) && getSource(it) != null }
    }

    fun allSourceIds(): List<String> = SourceRegistryMeta.SOURCE_META.map { it.id }

    fun resetInstances() {
        instances.clear()
    }

    fun priorityIds(): List<String> {
        val known = SourceRegistryMeta.SOURCE_META.map { it.id }
        val saved = config.getStringList("sources.priority").filter { known.contains(it) }
        return (saved + known.filterNot { saved.contains(it) }).distinct()
    }

    suspend fun searchAll(
        keyword: String,
        page: Int = 1,
        limit: Int = 20,
        sourceIds: List<String>? = null
    ): List<SearchGroup> = coroutineScope {
        val query = keyword.trim()
        if (query.isEmpty()) return@coroutineScope emptyList()
        val ids = (sourceIds ?: enabledSourceIds()).filter { SourceRegistryMeta.SOURCE_NAMES.containsKey(it) }
        if (ids.isEmpty()) return@coroutineScope emptyList()
        val results = ids.map { id ->
            async(Dispatchers.IO) {
                val source = getSource(id) ?: return@async null
                try {
                    val items = source.search(query, page, minOf(limit, source.searchLimit))
                    if (items.isEmpty()) null else SearchGroup(id, items, source.lastSearchTotal)
                } catch (error: Exception) {
                    log.w("SourceRegistry", "search failed " + id + ": " + error.message)
                    null
                }
            }
        }.awaitAll()
        val priority = priorityIds()
        results.filterNotNull().sortedBy { group -> priority.indexOf(group.source) }
    }

    fun qualityOrder(info: MusicInfo, quality: String = "320k", sourceId: String? = null): List<String> {
        val source = getSource(sourceId ?: info.source)
        val best = try {
            source?.getBestQuality(info, quality) ?: quality
        } catch (_: Exception) {
            quality
        }
        if (best == QualityLevel.AUTO || !QualityLevel.ALL.contains(best)) {
            return SourceRegistryMeta.RESOLVE_QUALITY_ORDER.toList()
        }
        return listOf(best) + SourceRegistryMeta.RESOLVE_QUALITY_ORDER.filter { it != best }
    }

    fun getMusicUrlExact(info: MusicInfo, quality: String, sourceId: String? = null): String? {
        val source = getSource(sourceId ?: info.source) ?: return null
        return try {
            source.getMusicUrl(info, quality)
        } catch (error: Exception) {
            log.w("SourceRegistry", "url failed " + info.source + ": " + error.message)
            null
        }
    }

    fun getMusicUrl(info: MusicInfo, quality: String = "320k", sourceId: String? = null): String? {
        for (candidate in qualityOrder(info, quality, sourceId)) {
            val url = getMusicUrlExact(info, candidate, sourceId)
            if (!url.isNullOrBlank()) return url
        }
        return null
    }

    fun getLyric(info: MusicInfo, sourceId: String? = null): String? {
        val source = getSource(sourceId ?: info.source) ?: return null
        return try {
            source.getLyric(info)
        } catch (error: Exception) {
            log.w("SourceRegistry", "lyric failed " + info.source + ": " + error.message)
            null
        }
    }

    fun getPicUrl(info: MusicInfo, sourceId: String? = null): String? {
        val source = getSource(sourceId ?: info.source) ?: return null
        return try {
            source.getPicUrl(info)
        } catch (error: Exception) {
            log.w("SourceRegistry", "pic failed " + info.source + ": " + error.message)
            null
        }
    }

    fun downloadHeaders(sourceId: String): Map<String, String> {
        return try {
            getSource(sourceId)?.getDownloadHeaders() ?: emptyMap()
        } catch (_: Exception) {
            emptyMap()
        }
    }

    fun downloadCookies(sourceId: String): Map<String, String> {
        return try {
            getSource(sourceId)?.getDownloadCookies() ?: emptyMap()
        } catch (_: Exception) {
            emptyMap()
        }
    }

    suspend fun resolveTrack(
        info: MusicInfo,
        quality: String = "320k",
        excludedSources: List<String> = emptyList(),
        limit: Int = 20
    ): FallbackResult? = coroutineScope {
        if (info.name.isBlank()) return@coroutineScope null
        val excluded = (excludedSources + info.source).toSet()
        val ids = priorityIds().filter { !excluded.contains(it) && getSource(it) != null }
        if (ids.isEmpty()) return@coroutineScope null
        val keyword = (info.name + " " + info.singer).trim().ifEmpty { info.name }
        val order = qualityOrder(info, quality)
        val results = ids.map { id ->
            async(Dispatchers.IO) {
                val source = getSource(id) ?: return@async null
                try {
                    val preferOriginal = config.getBoolean("sources.prefer_original", true)
                    val candidates = source.search(keyword, page = 1, limit = limit)
                        .filter { durationMatches(it, info.interval) }
                        .sortedWith(
                            compareBy(
                                { if (preferOriginal && it.isOriginal) 0 else 1 },
                                { kotlin.math.abs(it.interval - info.interval) }
                            )
                        )
                    for (candidate in candidates) {
                        for (candidateQuality in order) {
                            val url = try {
                                source.getMusicUrl(candidate, candidateQuality)
                            } catch (_: Exception) {
                                null
                            }
                            if (!url.isNullOrBlank()) {
                                return@async FallbackResult(candidate, url, candidateQuality)
                            }
                        }
                    }
                    null
                } catch (error: Exception) {
                    log.w("SourceRegistry", "fallback failed " + id + ": " + error.message)
                    null
                }
            }
        }.awaitAll()
        results.firstOrNull { it != null }
    }
}
