package com.fusionlab.fusionmusic.ui.album

import android.widget.Toast
import androidx.compose.foundation.clickable
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
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.data.source.AlbumInfo
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.TrackRow
import com.fusionlab.fusionmusic.ui.download.BatchDownloadButton
import com.fusionlab.fusionmusic.ui.navigation.LocalCatalogNavigator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun AlbumScreen(
    container: AppContainer,
    albumId: String,
    albumName: String,
    artistName: String,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val navigator = LocalCatalogNavigator.current
    var page by remember { mutableStateOf<AlbumInfo?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }

    LaunchedEffect(albumId, albumName, artistName) {
        loading = true
        error = ""
        val catalog = container.neteaseCatalog
        val result = withContext(Dispatchers.IO) {
            try {
                catalog.albumPage(albumId, albumName, artistName)
            } catch (_: Exception) {
                null
            }
        }
        page = result
        loading = false
        if (result == null) error = "没有找到这张专辑的资料"
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("专辑", style = MaterialTheme.typography.titleLarge)
        }
        when {
            loading -> Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            page == null -> Text(
                error.ifBlank { "没有找到这张专辑的资料" },
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp)
            )
            else -> {
                val info = page ?: return@Column
                val songs = info.songs
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
                                modifier = Modifier.size(112.dp).clip(RoundedCornerShape(10.dp))
                            )
                            Column(modifier = Modifier.padding(start = 14.dp).weight(1f)) {
                                Text(
                                    info.name,
                                    style = MaterialTheme.typography.titleLarge,
                                    fontWeight = FontWeight.SemiBold,
                                    maxLines = 2,
                                    overflow = TextOverflow.Ellipsis
                                )
                                if (info.artistNames.isNotBlank()) {
                                    Text(
                                        info.artistNames,
                                        style = MaterialTheme.typography.bodyMedium,
                                        modifier = Modifier.then(
                                            if (navigator != null) {
                                                Modifier.clickable {
                                                    navigator.openArtist(info.artists.firstOrNull()?.id ?: "", info.artistNames)
                                                }
                                            } else {
                                                Modifier
                                            }
                                        )
                                    )
                                }
                                val meta = listOf(info.typeText, info.publishText, info.company)
                                    .filter { it.isNotBlank() }.joinToString(" · ")
                                if (meta.isNotBlank()) {
                                    Text(
                                        meta,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        modifier = Modifier.padding(top = 4.dp)
                                    )
                                }
                                Text(
                                    "共 " + (if (info.size > 0) info.size else songs.size) + " 首",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                        if (info.description.isNotBlank()) {
                            Text(
                                info.description,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 5,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                            )
                        }
                        BatchDownloadButton(container, songs.map { Track.fromMusicInfo(it) })
                        Text(
                            "曲目",
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(start = 16.dp, top = 14.dp, bottom = 4.dp)
                        )
                    }
                    itemsIndexed(songs, key = { _, track -> track.source + ":" + track.songmid }) { index, song ->
                        TrackRow(
                            track = Track.fromMusicInfo(song),
                            onPlay = {
                                PlaybackController.playTracks(context, songs.map { Track.fromMusicInfo(it) }, index)
                            },
                            onPlayNext = {
                                container.playbackRepository.insertNext(Track.fromMusicInfo(song))
                                Toast.makeText(context, "已加入下一首", Toast.LENGTH_SHORT).show()
                            },
                            onAddToQueue = {
                                container.playbackRepository.appendToQueue(Track.fromMusicInfo(song))
                                Toast.makeText(context, "已加入队列", Toast.LENGTH_SHORT).show()
                            },
                            onFavorite = {
                                val added = container.library.toggleFavorite(Track.fromMusicInfo(song))
                                Toast.makeText(context, if (added) "已收藏" else "已取消收藏", Toast.LENGTH_SHORT).show()
                            },
                            onDownload = { container.downloadRepository.requestDownload(Track.fromMusicInfo(song)) }
                        )
                    }
                }
            }
        }
    }
}
