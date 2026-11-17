package com.fusionlab.fusionmusic.ui.discover

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.MusicInfo
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.source.DiscoverPlaylist
import com.fusionlab.fusionmusic.data.source.NeteaseExtras
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import com.fusionlab.fusionmusic.data.source.ToplistInfo
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.TrackRow
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun DiscoverScreen(
    container: AppContainer,
    onOpenPlaylist: (String) -> Unit
) {
    var loading by remember { mutableStateOf(true) }
    var playlists by remember { mutableStateOf<List<DiscoverPlaylist>>(emptyList()) }
    var newSongs by remember { mutableStateOf<List<MusicInfo>>(emptyList()) }
    var toplists by remember { mutableStateOf<List<ToplistInfo>>(emptyList()) }
    var error by remember { mutableStateOf<String?>(null) }
    var reloadToken by remember { mutableStateOf(0) }
    val context = LocalContext.current

    LaunchedEffect(reloadToken) {
        loading = true
        error = null
        val result = withContext(Dispatchers.IO) {
            val source = container.sourceRegistry.getSource("wy") as? NeteaseSource
            if (source == null) {
                null
            } else {
                val extras = NeteaseExtras(source)
                Triple(extras.recommendPlaylists(12), extras.newSongs(12), extras.toplists())
            }
        }
        if (result == null) {
            error = "网易云音源不可用"
        } else {
            playlists = result.first
            newSongs = result.second
            toplists = result.third
        }
        loading = false
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("发现音乐", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            IconButton(onClick = { reloadToken += 1 }) {
                Icon(Icons.Outlined.Refresh, contentDescription = "刷新")
            }
        }
        if (loading) {
            CircularProgressIndicator(modifier = Modifier.padding(24.dp))
            return@Column
        }
        if (error != null) {
            Text(error ?: "", modifier = Modifier.padding(24.dp), color = MaterialTheme.colorScheme.error)
            return@Column
        }
        LazyColumn(modifier = Modifier.fillMaxSize()) {
            if (playlists.isNotEmpty()) {
                item {
                    Text(
                        "推荐歌单",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                }
                item {
                    LazyRow(
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        items(playlists, key = { it.id }) { playlist ->
                            Column(
                                modifier = Modifier.size(width = 140.dp, height = 190.dp)
                                    .clickable { onOpenPlaylist(playlist.id) }
                            ) {
                                AsyncImage(
                                    model = playlist.cover,
                                    contentDescription = null,
                                    contentScale = ContentScale.Crop,
                                    modifier = Modifier.size(140.dp).clip(RoundedCornerShape(10.dp))
                                )
                                Text(
                                    playlist.name,
                                    style = MaterialTheme.typography.bodyMedium,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                    modifier = Modifier.padding(top = 4.dp)
                                )
                                Text(
                                    playlist.trackCount.toString() + " 首",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }
            if (toplists.isNotEmpty()) {
                item {
                    Text(
                        "排行榜",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                }
                items(toplists, key = { it.id }) { toplist ->
                    Row(
                        modifier = Modifier.fillMaxWidth().clickable { onOpenPlaylist(toplist.id) }
                            .padding(horizontal = 16.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        AsyncImage(
                            model = toplist.cover,
                            contentDescription = null,
                            contentScale = ContentScale.Crop,
                            modifier = Modifier.size(44.dp).clip(RoundedCornerShape(6.dp))
                        )
                        Column(modifier = Modifier.padding(start = 12.dp)) {
                            Text(toplist.name, style = MaterialTheme.typography.bodyMedium)
                            Text(
                                toplist.updateFrequency,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }
            if (newSongs.isNotEmpty()) {
                item {
                    Text(
                        "最新音乐",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                }
                val tracks = newSongs.map { Track.fromMusicInfo(it) }
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
