package com.fusionlab.fusionmusic.ui.search

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.AddToPlaylistDialog
import com.fusionlab.fusionmusic.ui.components.TrackRow
import com.fusionlab.fusionmusic.ui.download.BatchDownloadButton

@Composable
fun SearchScreen(container: AppContainer) {
    val vm: SearchViewModel = viewModel(
        factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T {
                return SearchViewModel(container.sourceRegistry, container.config) as T
            }
        }
    )
    val context = LocalContext.current
    val tracks = vm.tracks()
    var selectedUids by remember { mutableStateOf<Set<String>>(emptySet()) }
    var playlistDialog by remember { mutableStateOf(false) }
    val selectionMode = selectedUids.isNotEmpty()
    val selectedTracks = tracks.filter { selectedUids.contains(it.uid) }
    val toggleSelection: (String) -> Unit = { uid ->
        selectedUids = if (selectedUids.contains(uid)) selectedUids - uid else selectedUids + uid
    }
    LaunchedEffect(vm.groups) { selectedUids = emptySet() }
    if (playlistDialog) {
        AddToPlaylistDialog(container, selectedTracks) { playlistDialog = false }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = vm.query,
                onValueChange = { vm.onQueryChange(it) },
                modifier = Modifier.weight(1f),
                singleLine = true,
                placeholder = { Text("搜索歌曲、歌手、专辑") },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                keyboardActions = KeyboardActions(onSearch = { vm.search() })
            )
            IconButton(onClick = { vm.search() }) {
                Icon(Icons.Outlined.Search, contentDescription = "搜索")
            }
        }

        if (vm.tabs().size > 1) {
            LazyRow(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(vm.tabs(), key = { it.first }) { tab ->
                    FilterChip(
                        selected = vm.selectedSource == tab.first,
                        onClick = { vm.selectSource(tab.first) },
                        label = { Text(tab.second) }
                    )
                }
            }
        }

        if (vm.suggestions.isNotEmpty() && !vm.loading) {
            LazyRow(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 2.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(vm.suggestions) { suggestion ->
                    FilterChip(
                        selected = false,
                        onClick = {
                            vm.onQueryChange(suggestion)
                            vm.search()
                        },
                        label = { Text(suggestion) }
                    )
                }
            }
        }

        if (tracks.isNotEmpty() && !vm.loading) {
            if (selectionMode) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("已选 " + selectedTracks.size + " 首", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                    androidx.compose.material3.TextButton(onClick = { playlistDialog = true }) { Text("加入歌单") }
                    androidx.compose.material3.TextButton(onClick = {
                        if (selectedTracks.isNotEmpty()) {
                            container.playbackRepository.extendQueue(selectedTracks)
                            Toast.makeText(context, "已加入队列", Toast.LENGTH_SHORT).show()
                        }
                    }) { Text("加入队列") }
                    BatchDownloadButton(container, selectedTracks, "下载选中")
                    androidx.compose.material3.TextButton(onClick = { selectedUids = emptySet() }) { Text("取消") }
                }
            } else {
                Row(modifier = Modifier.padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("共 " + tracks.size + " 首", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                    BatchDownloadButton(container, tracks)
                }
            }
        }

        if (vm.query.isBlank() && vm.history.isNotEmpty()) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text("最近搜索", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                androidx.compose.material3.TextButton(onClick = { vm.clearHistory() }) { Text("清空") }
            }
            LazyRow(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(vm.history) { keyword ->
                    FilterChip(
                        selected = false,
                        onClick = {
                            vm.onQueryChange(keyword)
                            vm.search()
                        },
                        label = { Text(keyword) }
                    )
                }
            }
        }

        when {
            vm.loading -> {
                CircularProgressIndicator(modifier = Modifier.padding(24.dp).align(Alignment.CenterHorizontally))
            }
            vm.error != null && tracks.isEmpty() -> {
                Text(
                    text = vm.error ?: "",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(24.dp)
                )
            }
            tracks.isEmpty() -> {
                Text(
                    text = if (vm.query.isBlank()) "输入关键词后按搜索" else "没有找到相关结果",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(24.dp)
                )
            }
            else -> {
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    itemsIndexed(tracks, key = { _, track -> track.uid }) { index, track ->
                        TrackRow(
                            track = track,
                            selected = selectedUids.contains(track.uid),
                            openPlayerOnClick = !selectionMode,
                            onPlay = {
                                if (selectionMode) toggleSelection(track.uid)
                                else PlaybackController.playTracks(context, tracks, index)
                            },
                            onLongClick = { toggleSelection(track.uid) },
                            onPlayNext = {
                                container.playbackRepository.insertNext(track)
                                Toast.makeText(context, "已加入下一首", Toast.LENGTH_SHORT).show()
                            },
                            onAddToQueue = {
                                container.playbackRepository.appendToQueue(track)
                                Toast.makeText(context, "已加入队列", Toast.LENGTH_SHORT).show()
                            },
                            onFavorite = {
                                val added = container.library.toggleFavorite(track)
                                Toast.makeText(context, if (added) "已收藏" else "已取消收藏", Toast.LENGTH_SHORT).show()
                            },
                            onDownload = { container.downloadRepository.requestDownload(track) }
                        )
                    }
                }
            }
        }
    }
}
