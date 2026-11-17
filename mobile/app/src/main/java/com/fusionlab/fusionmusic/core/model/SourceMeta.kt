package com.fusionlab.fusionmusic.core.model

data class SourceMeta(
    val id: String,
    val name: String,
    val short: String
)

object SourceRegistryMeta {
    val SOURCE_META: List<SourceMeta> = listOf(
        SourceMeta("wy", "网易云音乐", "网易云"),
        SourceMeta("tx", "QQ音乐", "QQ"),
        SourceMeta("kw", "酷我音乐", "酷我"),
        SourceMeta("kg", "酷狗音乐", "酷狗"),
        SourceMeta("mg", "咪咕音乐", "咪咕"),
        SourceMeta("bili", "哔哩哔哩", "B站")
    )

    val SOURCE_NAMES: Map<String, String> = SOURCE_META.associate { it.id to it.name }

    val DEFAULT_SEARCH_SOURCES: List<String> = listOf("wy", "tx", "kw", "kg", "mg")
    val FALLBACK_ONLY_SOURCES: List<String> = listOf("bili")
    val RESOLVE_QUALITY_ORDER: List<String> = listOf("flac24bit", "flac", "320k", "128k")

    fun display(source: String): String {
        if (source == "local") return "本地"
        return SOURCE_NAMES[source] ?: source
    }

    fun isSearchSource(source: String): Boolean = DEFAULT_SEARCH_SOURCES.contains(source)

    fun normalizeLegacyEnabled(values: List<String>): List<String> {
        val mapped = values.mapNotNull { value ->
            when (value) {
                "netease" -> "wy"
                "local" -> null
                else -> value
            }
        }.filter { SOURCE_NAMES.containsKey(it) }
        return mapped.ifEmpty { DEFAULT_SEARCH_SOURCES }
    }
}
