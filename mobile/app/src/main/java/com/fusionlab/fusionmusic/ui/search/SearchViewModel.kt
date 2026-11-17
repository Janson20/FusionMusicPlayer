package com.fusionlab.fusionmusic.ui.search

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.fusionlab.fusionmusic.core.model.SourceRegistryMeta
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.source.NeteaseExtras
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import com.fusionlab.fusionmusic.data.source.SearchGroup
import com.fusionlab.fusionmusic.data.source.SourceRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SearchViewModel(
    private val sources: SourceRegistry,
    private val config: ConfigRepository
) : ViewModel() {
    var query by mutableStateOf("")
    var loading by mutableStateOf(false)
    var groups by mutableStateOf<List<SearchGroup>>(emptyList())
    var selectedSource by mutableStateOf("all")
    var error by mutableStateOf<String?>(null)
    var suggestions by mutableStateOf<List<String>>(emptyList())
    var history by mutableStateOf(config.getStringList("search_history").take(12))
    private var job: Job? = null
    private var suggestJob: Job? = null

    fun onQueryChange(value: String) {
        query = value
        suggestJob?.cancel()
        if (value.isBlank()) {
            suggestions = emptyList()
            return
        }
        suggestJob = viewModelScope.launch {
            delay(250)
            val source = sources.getSource("wy") as? NeteaseSource ?: return@launch
            val result = try {
                withContext(Dispatchers.IO) {
                    NeteaseExtras(source).searchSuggest(value.trim(), 8)
                }
            } catch (_: Exception) {
                emptyList()
            }
            if (query.trim() == value.trim()) suggestions = result
        }
    }

    fun search() {
        val keyword = query.trim()
        if (keyword.isEmpty()) {
            error = "请输入搜索关键词"
            return
        }
        remember(keyword)
        suggestJob?.cancel()
        suggestions = emptyList()
        job?.cancel()
        loading = true
        error = null
        job = viewModelScope.launch {
            val result = try {
                sources.searchAll(keyword, page = 1, limit = 20)
            } catch (_: Exception) {
                emptyList()
            }
            groups = result
            loading = false
            selectedSource = "all"
            if (result.isEmpty()) error = "没有找到「" + keyword + "」的相关结果"
        }
    }

    fun clearHistory() {
        history = emptyList()
        config.setStringList("search_history", emptyList())
    }

    fun selectSource(source: String) {
        selectedSource = source
    }

    fun tracks(): List<Track> {
        val list = if (selectedSource == "all") {
            val order = sources.priorityIds()
            groups.sortedBy { group -> order.indexOf(group.source) }.flatMap { it.results }
        } else {
            groups.firstOrNull { it.source == selectedSource }?.results ?: emptyList()
        }
        return list.map { Track.fromMusicInfo(it) }
    }

    fun tabs(): List<Pair<String, String>> {
        val tabs = mutableListOf("all" to "全部")
        val metaById = SourceRegistryMeta.SOURCE_META.associateBy { it.id }
        for (id in sources.priorityIds()) {
            if (groups.any { it.source == id }) tabs.add(id to (metaById[id]?.short ?: id))
        }
        return tabs
    }

    private fun remember(keyword: String) {
        val next = (listOf(keyword) + history.filterNot { it.equals(keyword, ignoreCase = true) }).take(12)
        history = next
        config.setStringList("search_history", next)
    }
}
