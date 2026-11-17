package com.fusionlab.fusionmusic.ui.discover

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.source.NeteaseExtras
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import com.fusionlab.fusionmusic.data.source.PlaylistInfo
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.AddToPlaylistDialog
import com.fusionlab.fusionmusic.ui.components.TrackRow
import com.fusionlab.fusionmusic.ui.download.BatchDownloadButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun PlaylistDetailScreen(
    container: AppContainer,
    playlistId: String,
    onBack: () -> Unit
) {
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var meta by remember { mutableStateOf<PlaylistInfo?>(null) }
    var tracks by remember { mutableStateOf<List<Track>>(emptyList()) }
    var selectedUids by remember { mutableStateOf<Set<String>>(emptySet()) }
    var playlistDialog by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val selectionMode = selectedUids.isNotEmpty()
    val selectedTracks = tracks.filter { selectedUids.contains(it.uid) }
    val toggleSelection: (String) -> Unit = { uid ->
        selectedUids = if (selectedUids.contains(uid)) selectedUids - uid else selectedUids + uid
    }
    LaunchedEffect(tracks) { selectedUids = emptySet() }
    if (playlistDialog) {
        AddToPlaylistDialog(container, selectedTracks) { playlistDialog = false }
    }

    LaunchedEffect(playlistId) {
        loading = true
        error = null
        val result = withContext(Dispatchers.IO) {
            val source = container.sourceRegistry.getSource("wy") as? NeteaseSource
            if (source == null) null else {
                val extras = NeteaseExtras(source)
                val info = extras.playlistMeta(playlistId)
                val songs = extras.playlistTracks(playlistId)
                Pair(info, songs)
            }
        }
        if (result == null) {
            error = "歌单加载失败"
        } else {
            meta = result.first
            tracks = result.second.map { Track.fromMusicInfo(it) }
        }
        loading = false
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(modifier = Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("歌单", style = MaterialTheme.typography.titleLarge)
        }
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
                    }
                }) { Text("加入队列") }
                BatchDownloadButton(container, selectedTracks, "下载选中")
                androidx.compose.material3.TextButton(onClick = { selectedUids = emptySet() }) { Text("取消") }
            }
        }
        when {
            loading -> CircularProgressIndicator(modifier = Modifier.padding(24.dp))
            error != null -> Text(error ?: "", modifier = Modifier.padding(24.dp), color = MaterialTheme.colorScheme.error)
            else -> {
                val info = meta
                if (info != null) {
                    Row(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                        AsyncImage(
                            model = info.cover,
                            contentDescription = null,
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.size(120.dp).clip(RoundedCornerShape(12.dp))
                        )
                        Column(modifier = Modifier.padding(start = 12.dp)) {
                            Text(info.name, style = MaterialTheme.typography.titleLarge)
                            Text(info.creator, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(info.trackCount.toString() + " 首", style = MaterialTheme.typography.bodySmall)
                            Button(
                                onClick = {
                                    if (tracks.isNotEmpty()) PlaybackController.playTracks(context, tracks, 0)
                                },
                                modifier = Modifier.padding(top = 8.dp)
                            ) { Text("播放全部") }
                            BatchDownloadButton(container, tracks)
                        }
                    }
                }
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
                            onPlayNext = { container.playbackRepository.insertNext(track) },
                            onAddToQueue = { container.playbackRepository.appendToQueue(track) },
                            onFavorite = { container.library.toggleFavorite(track) },
                            onDownload = { container.downloadRepository.requestDownload(track) }
                        )
                    }
                }
            }
        }
    }
}
