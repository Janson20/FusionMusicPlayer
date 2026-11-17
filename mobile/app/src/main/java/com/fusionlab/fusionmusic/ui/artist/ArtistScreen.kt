package com.fusionlab.fusionmusic.ui.artist

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.data.source.ArtistInfo
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.TrackRow
import com.fusionlab.fusionmusic.ui.download.BatchDownloadButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun ArtistScreen(
    container: AppContainer,
    artistId: String,
    artistName: String,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    var page by remember { mutableStateOf<ArtistInfo?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }

    LaunchedEffect(artistId, artistName) {
        loading = true
        error = ""
        val catalog = container.neteaseCatalog
        val result = withContext(Dispatchers.IO) {
            try {
                catalog.artistPage(artistId, artistName)
            } catch (_: Exception) {
                null
            }
        }
        page = result
        loading = false
        if (result == null) error = "没有找到这个歌手的资料"
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("歌手", style = MaterialTheme.typography.titleLarge)
        }
        when {
            loading -> Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            page == null -> Text(
                error.ifBlank { "没有找到这个歌手的资料" },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp)
            )
            else -> {
                val info = page ?: return@Column
                val songs = info.hotSongs
                LazyColumn(modifier = Modifier.fillMaxSize()) {
                    item {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(16.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            AsyncImage(
                                model = info.cover.ifBlank { null },
                                contentDescription = null,
                                contentScale = ContentScale.Crop,
                                modifier = Modifier.size(108.dp).clip(RoundedCornerShape(54.dp))
                            )
                            Column(modifier = Modifier.padding(start = 14.dp).weight(1f)) {
                                Text(
                                    info.name,
                                    style = MaterialTheme.typography.headlineSmall,
                                    fontWeight = FontWeight.SemiBold
                                )
                                if (info.alias.isNotEmpty()) {
                                    Text(
                                        info.alias.joinToString(" / "),
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis
                                    )
                                }
                                Text(
                                    "单曲 " + info.musicSize + " · 专辑 " + info.albumSize + " · MV " + info.mvSize,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(top = 4.dp)
                                )
                            }
                        }
                        if (info.briefDesc.isNotBlank()) {
                            Text(
                                info.briefDesc,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 4,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                            )
                        }
                        BatchDownloadButton(container, songs.map { com.fusionlab.fusionmusic.core.model.Track.fromMusicInfo(it) })
                        Text(
                            "热门歌曲",
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(start = 16.dp, top = 14.dp, bottom = 4.dp)
                        )
                    }
                    itemsIndexed(songs, key = { _, track -> track.source + ":" + track.songmid }) { index, track ->
                        TrackRow(
                            track = com.fusionlab.fusionmusic.core.model.Track.fromMusicInfo(track),
                            onPlay = {
                                val tracks = songs.map { com.fusionlab.fusionmusic.core.model.Track.fromMusicInfo(it) }
                                PlaybackController.playTracks(context, tracks, index)
                            },
                            onPlayNext = {
                                container.playbackRepository.insertNext(
                                    com.fusionlab.fusionmusic.core.model.Track.fromMusicInfo(track)
                                )
                                Toast.makeText(context, "已加入下一首", Toast.LENGTH_SHORT).show()
                            },
                            onAddToQueue = {
                                container.playbackRepository.appendToQueue(
                                    com.fusionlab.fusionmusic.core.model.Track.fromMusicInfo(track)
                                )
                                Toast.makeText(context, "已加入队列", Toast.LENGTH_SHORT).show()
                            },
                            onFavorite = {
                                val added = container.library.toggleFavorite(
                                    com.fusionlab.fusionmusic.core.model.Track.fromMusicInfo(track)
                                )
                                Toast.makeText(context, if (added) "已收藏" else "已取消收藏", Toast.LENGTH_SHORT).show()
                            },
                            onDownload = {
                                container.downloadRepository.requestDownload(
                                    com.fusionlab.fusionmusic.core.model.Track.fromMusicInfo(track)
                                )
                            }
                        )
                    }
                    item { Box(modifier = Modifier.size(1.dp)) }
                }
            }
        }
    }
}
