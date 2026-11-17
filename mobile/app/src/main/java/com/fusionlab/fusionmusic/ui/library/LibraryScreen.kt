package com.fusionlab.fusionmusic.ui.library

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Add
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.ListItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.store.Playlist
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.AddToPlaylistDialog
import com.fusionlab.fusionmusic.ui.components.TrackRow
import com.fusionlab.fusionmusic.ui.download.BatchDownloadButton

@Composable
fun LibraryScreen(container: AppContainer) {
    val library = container.library
    var tab by remember { mutableStateOf("favorites") }
    var favorites by remember { mutableStateOf(library.favorites()) }
    var history by remember { mutableStateOf(library.history()) }
    var playlists by remember { mutableStateOf(library.userPlaylists()) }
    var selectedPlaylist by remember { mutableStateOf<Playlist?>(null) }
    var newPlaylistDialog by remember { mutableStateOf(false) }
    var newPlaylistName by remember { mutableStateOf("") }
    val context = LocalContext.current

    DisposableEffect(Unit) {
        val listener: (String) -> Unit = {
            favorites = library.favorites()
            history = library.history()
            playlists = library.userPlaylists()
            selectedPlaylist = selectedPlaylist?.let { library.getPlaylist(it.id) }
        }
        library.addListener(listener)
        onDispose { library.removeListener(listener) }
    }

    if (newPlaylistDialog) {
        AlertDialog(
            onDismissRequest = { newPlaylistDialog = false },
            title = { Text("新建歌单") },
            text = {
                OutlinedTextField(
                    value = newPlaylistName,
                    onValueChange = { newPlaylistName = it },
                    singleLine = true,
                    label = { Text("歌单名称") }
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    library.createPlaylist(newPlaylistName.ifBlank { "新建歌单" })
                    newPlaylistName = ""
                    newPlaylistDialog = false
                }) { Text("创建") }
            },
            dismissButton = {
                TextButton(onClick = { newPlaylistDialog = false }) { Text("取消") }
            }
        )
    }

    if (selectedPlaylist != null) {
        val playlist = selectedPlaylist ?: return
        val tracks = playlist.songs
        Column(modifier = Modifier.fillMaxSize()) {
            Row(modifier = Modifier.fillMaxWidth().padding(8.dp)) {
                IconButton(onClick = { selectedPlaylist = null }) {
                    Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
                }
                Column(modifier = Modifier.weight(1f)) {
                    Text(playlist.name, style = MaterialTheme.typography.titleLarge)
                    Text(tracks.size.toString() + " 首", style = MaterialTheme.typography.bodySmall)
                }
            }
            Row(modifier = Modifier.padding(horizontal = 16.dp)) {
                BatchDownloadButton(container, tracks)
            }
            if (tracks.isEmpty()) {
                Text("歌单是空的", modifier = Modifier.padding(24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else {
                LazyColumn {
                    itemsIndexed(tracks, key = { _, track -> track.uid }) { index, track ->
                        TrackRow(
                            track = track,
                            onPlay = { PlaybackController.playTracks(context, tracks, index) },
                            onPlayNext = { container.playbackRepository.insertNext(track) },
                            onAddToQueue = { container.playbackRepository.appendToQueue(track) },
                            onFavorite = { library.toggleFavorite(track) },
                            onDownload = { container.downloadRepository.requestDownload(track) }
                        )
                    }
                }
            }
        }
        return
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            FilterChip(selected = tab == "favorites", onClick = { tab = "favorites" }, label = { Text("我喜欢的音乐") })
            FilterChip(selected = tab == "history", onClick = { tab = "history" }, label = { Text("最近播放") })
            FilterChip(selected = tab == "playlists", onClick = { tab = "playlists" }, label = { Text("歌单") })
        }

        when (tab) {
            "favorites" -> TrackList(container, favorites, emptyMessage = "还没有收藏的歌曲")
            "history" -> TrackList(container, history, emptyMessage = "还没有播放记录")
            else -> {
                Row(modifier = Modifier.fillMaxWidth().padding(12.dp), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = { newPlaylistDialog = true }) {
                        Icon(Icons.Outlined.Add, contentDescription = null)
                        Text("新建歌单")
                    }
                }
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    items(playlists, key = { it.id }) { playlist ->
                        ListItem(
                            headlineContent = { Text(playlist.name) },
                            supportingContent = { Text(playlist.count.toString() + " 首") },
                            modifier = Modifier.fillMaxWidth()
                        )
                        androidx.compose.foundation.layout.Box(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp)
                        ) {
                            TextButton(onClick = { selectedPlaylist = playlist }) { Text("打开") }
                            TextButton(onClick = { library.deletePlaylist(playlist.id) }) { Text("删除") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TrackList(container: AppContainer, tracks: List<Track>, emptyMessage: String) {
    val context = LocalContext.current
    if (tracks.isEmpty()) {
        Text(emptyMessage, modifier = Modifier.padding(24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        return
    }
    var selectedUids by remember { mutableStateOf<Set<String>>(emptySet()) }
    var playlistDialog by remember { mutableStateOf(false) }
    val selectionMode = selectedUids.isNotEmpty()
    val selectedTracks = tracks.filter { selectedUids.contains(it.uid) }
    val toggle: (String) -> Unit = { uid ->
        selectedUids = if (selectedUids.contains(uid)) selectedUids - uid else selectedUids + uid
    }
    LaunchedEffect(tracks) { selectedUids = emptySet() }
    if (playlistDialog) {
        AddToPlaylistDialog(container, selectedTracks) { playlistDialog = false }
    }
    Column(modifier = Modifier.fillMaxSize()) {
        if (selectionMode) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically
            ) {
                Text("已选 " + selectedTracks.size + " 首", style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
                TextButton(onClick = { playlistDialog = true }) { Text("加入歌单") }
                TextButton(onClick = {
                    if (selectedTracks.isNotEmpty()) {
                        container.playbackRepository.extendQueue(selectedTracks)
                        Toast.makeText(context, "已加入队列", Toast.LENGTH_SHORT).show()
                    }
                }) { Text("加入队列") }
                BatchDownloadButton(container, selectedTracks, "下载选中")
                TextButton(onClick = { selectedUids = emptySet() }) { Text("取消") }
            }
        }
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            itemsIndexed(tracks, key = { _, track -> track.uid }) { index, track ->
                TrackRow(
                    track = track,
                    selected = selectedUids.contains(track.uid),
                    openPlayerOnClick = !selectionMode,
                    onPlay = {
                        if (selectionMode) toggle(track.uid)
                        else PlaybackController.playTracks(context, tracks, index)
                    },
                    onLongClick = { toggle(track.uid) },
                    onPlayNext = { container.playbackRepository.insertNext(track) },
                    onAddToQueue = { container.playbackRepository.appendToQueue(track) },
                    onFavorite = { container.library.toggleFavorite(track) },
                    onDownload = { container.downloadRepository.requestDownload(track) }
                )
            }
        }
    }
}
