package com.fusionlab.fusionmusic.ui.player

import androidx.compose.foundation.gestures.detectDragGesturesAfterLongPress
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.zIndex
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material.icons.outlined.Repeat
import androidx.compose.material.icons.outlined.Shuffle
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.PlayMode
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.TrackRow

@Composable
fun QueueScreen(container: AppContainer, onBack: () -> Unit) {
    val snapshot by container.playbackRepository.snapshot.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var dragUid by remember { mutableStateOf<String?>(null) }
    var dragOffset by remember { mutableFloatStateOf(0f) }
    val currentQueue by rememberUpdatedState(snapshot.queue)
    Column(modifier = Modifier.fillMaxSize()) {
        Row(modifier = Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("播放队列", style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
            TextButton(onClick = { container.playbackRepository.cycleMode() }) {
                Icon(
                    imageVector = if (snapshot.mode == PlayMode.SHUFFLE) Icons.Outlined.Shuffle else Icons.Outlined.Repeat,
                    contentDescription = null
                )
                Text(snapshot.mode.label)
            }
            TextButton(onClick = {
                container.playbackRepository.clearQueue()
                PlaybackController.stop(context)
            }) { Text("清空") }
        }
        if (snapshot.queue.isEmpty()) {
            Text(
                text = "播放队列是空的",
                modifier = Modifier.padding(24.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        } else {
            Text(
                "长按歌曲拖动排序",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp)
            )
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                itemsIndexed(snapshot.queue, key = { _, track -> track.uid }) { index, track ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .zIndex(if (dragUid == track.uid) 1f else 0f)
                            .offset { IntOffset(0, if (dragUid == track.uid) dragOffset.roundToInt() else 0) }
                            .pointerInput(track.uid) {
                                detectDragGesturesAfterLongPress(
                                    onDragStart = {
                                        dragUid = track.uid
                                        dragOffset = 0f
                                    },
                                    onDrag = { change, amount ->
                                        change.consume()
                                        dragOffset += amount.y
                                        val queue = currentQueue
                                        val from = queue.indexOfFirst { it.uid == track.uid }
                                        if (from < 0) return@detectDragGesturesAfterLongPress
                                        val threshold = 56.dp.toPx()
                                        if (dragOffset > threshold && from < queue.lastIndex) {
                                            container.playbackRepository.moveQueueItem(from, from + 1)
                                            dragOffset -= threshold
                                        } else if (dragOffset < -threshold && from > 0) {
                                            container.playbackRepository.moveQueueItem(from, from - 1)
                                            dragOffset += threshold
                                        }
                                    },
                                    onDragEnd = {
                                        dragUid = null
                                        dragOffset = 0f
                                    },
                                    onDragCancel = {
                                        dragUid = null
                                        dragOffset = 0f
                                    }
                                )
                            },
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        TrackRow(
                            track = track,
                            active = index == snapshot.queueIndex,
                            showAlbum = false,
                            showSource = false,
                            onPlay = {
                                container.playbackRepository.playIndex(index)
                                PlaybackController.playIndex(context, index)
                            },
                            onFavorite = { container.library.toggleFavorite(track) },
                            onRemoveFromQueue = {
                                val wasCurrent = index == snapshot.queueIndex
                                container.playbackRepository.removeAt(index)
                                if (wasCurrent) {
                                    val next = container.playbackRepository.queue.index
                                    if (next >= 0) PlaybackController.playIndex(context, next)
                                }
                            },
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                }
            }
        }
    }
}
