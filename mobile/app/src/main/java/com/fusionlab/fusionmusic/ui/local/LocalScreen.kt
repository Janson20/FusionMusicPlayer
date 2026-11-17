package com.fusionlab.fusionmusic.ui.local

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.ui.components.TrackRow

@Composable
fun LocalScreen(container: AppContainer) {
    val repository = container.localRepository
    val state by repository.state.collectAsStateWithLifecycle()
    val tracks by repository.tracks.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val folderPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenDocumentTree()
    ) { uri ->
        if (uri != null) {
            if (repository.addFolder(uri)) repository.scan()
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Button(onClick = { folderPicker.launch(null) }) { Text("添加文件夹") }
            TextButton(onClick = { repository.scan() }) { Text("重新扫描") }
            if (state.scanning) TextButton(onClick = { repository.cancel() }) { Text("取消") }
        }
        if (state.scanning) {
            Text(
                state.phase + "  " + state.current + "/" + state.total,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        } else if (state.message.isNotBlank()) {
            Text(
                state.message,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp)
            )
        }

        val folders = repository.folders()
        if (folders.isNotEmpty()) {
            Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
                for (folder in folders) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            folder.substringAfterLast('/').ifBlank { folder },
                            style = MaterialTheme.typography.bodySmall,
                            modifier = Modifier.weight(1f)
                        )
                        TextButton(onClick = { repository.removeFolder(folder) }) { Text("移除") }
                    }
                }
            }
        }

        if (tracks.isEmpty()) {
            Text(
                "还没有本地音乐。添加一个文件夹后点「重新扫描」。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp)
            )
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                itemsIndexed(tracks, key = { _, track -> track.uid }) { index, track ->
                    TrackRow(
                        track = track,
                        onPlay = { PlaybackController.playTracks(context, tracks, index) },
                        onPlayNext = { container.playbackRepository.insertNext(track) },
                        onAddToQueue = { container.playbackRepository.appendToQueue(track) },
                        onFavorite = {
                            val added = container.library.toggleFavorite(track)
                            Toast.makeText(context, if (added) "已收藏" else "已取消收藏", Toast.LENGTH_SHORT).show()
                        },
                        onDownload = {
                            Toast.makeText(context, "本地曲目不需要下载", Toast.LENGTH_SHORT).show()
                        }
                    )
                }
            }
        }
    }
}
