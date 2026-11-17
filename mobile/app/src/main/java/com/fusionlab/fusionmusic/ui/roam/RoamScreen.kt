package com.fusionlab.fusionmusic.ui.roam

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Refresh
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.source.NeteaseExtras
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.TrackRow
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun RoamScreen(container: AppContainer) {
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var items by remember { mutableStateOf<List<Pair<MusicInfo, String>>>(emptyList()) }
    var reloadToken by remember { mutableStateOf(0) }
    val context = LocalContext.current
    val tracks = remember(items) { items.map { pair -> Track.fromMusicInfo(pair.first).apply { reason = pair.second } } }

    LaunchedEffect(reloadToken) {
        loading = true
        error = null
        val result = withContext(Dispatchers.IO) {
            val source = container.sourceRegistry.getSource("wy") as? NeteaseSource
            if (source == null) null else NeteaseExtras(source).roamBatch(15)
        }
        if (result == null) {
            error = "漫游加载失败"
        } else {
            items = result
        }
        loading = false
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("漫游", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            IconButton(onClick = { reloadToken += 1 }) {
                Icon(Icons.Outlined.Refresh, contentDescription = "换一批")
            }
        }
        when {
            loading -> CircularProgressIndicator(modifier = Modifier.padding(24.dp))
            error != null -> Text(error ?: "", modifier = Modifier.padding(24.dp), color = MaterialTheme.colorScheme.error)
            tracks.isEmpty() -> Text("暂时没有推荐", modifier = Modifier.padding(24.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
            else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                itemsIndexed(tracks, key = { _, track -> track.uid }) { index, track ->
                    TrackRow(
                        track = track,
                        onPlay = { PlaybackController.playTracks(context, tracks, index) },
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
