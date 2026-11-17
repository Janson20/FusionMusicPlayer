package com.fusionlab.fusionmusic.ui.components

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.ui.navigation.LocalCatalogNavigator
import com.fusionlab.fusionmusic.ui.navigation.LocalPlayerNavigator

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun TrackRow(
    track: Track,
    modifier: Modifier = Modifier,
    active: Boolean = false,
    selected: Boolean = false,
    openPlayerOnClick: Boolean = true,
    showAlbum: Boolean = true,
    showSource: Boolean = true,
    onPlay: () -> Unit,
    onLongClick: (() -> Unit)? = null,
    onPlayNext: () -> Unit = {},
    onAddToQueue: () -> Unit = {},
    onFavorite: () -> Unit = {},
    onDownload: () -> Unit = {},
    onRemoveFromQueue: (() -> Unit)? = null
) {
    var menuOpen by remember { mutableStateOf(false) }
    val catalog = LocalCatalogNavigator.current
    val playerNavigator = LocalPlayerNavigator.current
    val singer = track.singer.substringBefore("、").substringBefore("/").substringBefore("&").trim()
        .ifBlank { track.singer }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(
                if (selected) MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.45f)
                else androidx.compose.ui.graphics.Color.Transparent
            )
            .combinedClickable(
                onClick = {
                    onPlay()
                    if (openPlayerOnClick) playerNavigator?.open()
                },
                onLongClick = onLongClick
            )
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        AsyncImage(
            model = track.cover.ifBlank { null },
            contentDescription = null,
            contentScale = ContentScale.Crop,
            modifier = Modifier.size(48.dp).clip(RoundedCornerShape(8.dp))
        )
        Column(
            modifier = Modifier.weight(1f).padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp)
        ) {
            Text(
                text = track.displayName,
                style = MaterialTheme.typography.bodyLarge,
                color = if (active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Row {
                Text(
                    text = track.singer,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.then(
                        if (catalog != null) Modifier.clickable { catalog.openArtist("", singer) } else Modifier
                    )
                )
                if (showAlbum && track.album.isNotBlank()) {
                    Text(
                        text = " · ",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = track.album,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.then(
                            if (catalog != null) {
                                Modifier.clickable {
                                    catalog.openAlbum(
                                        if (track.source == "wy") track.albumId else "",
                                        track.album,
                                        singer
                                    )
                                }
                            } else {
                                Modifier
                            }
                        )
                    )
                }
            }
        }
        if (showSource) {
            Text(
                text = if (track.isLocal) "本地" else track.sourceText,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Text(
            text = track.durationText,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(start = 8.dp)
        )
        IconButton(onClick = { menuOpen = true }) {
            Icon(Icons.Outlined.MoreVert, contentDescription = "更多")
        }
        DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
            DropdownMenuItem(text = { Text("下一首播放") }, onClick = { menuOpen = false; onPlayNext() })
            DropdownMenuItem(text = { Text("添加到队列") }, onClick = { menuOpen = false; onAddToQueue() })
            DropdownMenuItem(text = { Text("收藏 / 取消收藏") }, onClick = { menuOpen = false; onFavorite() })
            DropdownMenuItem(text = { Text("下载") }, onClick = { menuOpen = false; onDownload() })
            if (onRemoveFromQueue != null) {
                DropdownMenuItem(
                    text = { Text("从播放队列移除") },
                    onClick = { menuOpen = false; onRemoveFromQueue() }
                )
            }
        }
    }
}
