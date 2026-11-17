package com.fusionlab.fusionmusic.ui.download

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.core.content.FileProvider
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
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
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.model.qualityLabel
import com.fusionlab.fusionmusic.data.download.DownloadTask
import com.fusionlab.fusionmusic.playback.PlaybackController
import java.io.File

@Composable
fun DownloadsScreen(container: AppContainer) {
    val repository = container.downloadRepository
    val tasks by repository.tasks.collectAsStateWithLifecycle()
    val context = LocalContext.current

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text("下载", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            TextButton(onClick = { repository.clearFinished() }) { Text("清空已完成") }
        }
        if (tasks.isEmpty()) {
            Text(
                "还没有下载任务。歌曲菜单里的「下载」会出现在这里。",
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(24.dp)
            )
        } else {
            LazyColumn(modifier = Modifier.fillMaxSize()) {
                items(tasks, key = { it.id }) { task ->
                    DownloadRow(
                        task = task,
                        onCancel = { repository.cancel(task.id) },
                        onRetry = { repository.retry(task.id) },
                        onRemove = { repository.remove(task.id) },
                        onOpen = { openDownloaded(context, task.targetPath) },
                        onPlay = {
                            if (task.status == DownloadTask.STATUS_DONE && task.targetPath.isNotBlank()) {
                                val local = Track(
                                    source = Track.LOCAL_SOURCE,
                                    songmid = task.targetPath,
                                    name = task.track.name,
                                    singer = task.track.singer,
                                    album = task.track.album,
                                    interval = task.track.interval,
                                    cover = task.track.cover,
                                    path = task.targetPath
                                )
                                PlaybackController.playTracks(context, listOf(local), 0)
                            } else {
                                Toast.makeText(context, "文件还没下载完成", Toast.LENGTH_SHORT).show()
                            }
                        }
                    )
                }
            }
        }
    }
}

@Composable
private fun DownloadRow(
    task: DownloadTask,
    onCancel: () -> Unit,
    onRetry: () -> Unit,
    onRemove: () -> Unit,
    onOpen: () -> Unit,
    onPlay: () -> Unit
) {
    Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text(task.track.name, style = MaterialTheme.typography.bodyMedium, maxLines = 1)
                Text(
                    task.track.singer + " · " + statusText(task),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (task.status == DownloadTask.STATUS_FAILED) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1
                )
            }
            if (task.status == DownloadTask.STATUS_QUEUED || task.status == DownloadTask.STATUS_RUNNING) {
                TextButton(onClick = onCancel) { Text("取消") }
            } else if (task.status == DownloadTask.STATUS_DONE) {
                TextButton(onClick = onPlay) { Text("播放") }
                if (task.targetPath.isNotBlank()) {
                    TextButton(onClick = onOpen) { Text("打开") }
                }
                TextButton(onClick = onRemove) { Text("移除") }
            } else {
                TextButton(onClick = onRetry) { Text("重试") }
                TextButton(onClick = onRemove) { Text("移除") }
            }
        }
        if (task.status == DownloadTask.STATUS_RUNNING || task.status == DownloadTask.STATUS_QUEUED) {
            val progress = if (task.total > 0) (task.progress.toFloat() / task.total).coerceIn(0f, 1f) else 0f
            LinearProgressIndicator(
                progress = { progress },
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp)
            )
        }
        if (task.error.isNotBlank()) {
            Text(
                task.error,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(top = 2.dp)
            )
        }
        if (task.warning.isNotBlank()) {
            Text(
                task.warning,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = 2.dp)
            )
        }
    }
}

private fun openDownloaded(context: android.content.Context, path: String) {
    if (path.isBlank()) return
    try {
        val uri = if (path.startsWith("content://")) {
            Uri.parse(path)
        } else {
            FileProvider.getUriForFile(
                context,
                context.packageName + ".fileprovider",
                File(path)
            )
        }
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "audio/*")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    } catch (_: Exception) {
        Toast.makeText(context, "没有可以打开这个文件的应用", Toast.LENGTH_SHORT).show()
    }
}

private fun statusText(task: DownloadTask): String = when (task.status) {
    DownloadTask.STATUS_QUEUED -> "等待中"
    DownloadTask.STATUS_RUNNING -> "下载中 " + percent(task)
    DownloadTask.STATUS_DONE -> "已完成 · " + (task.actualQuality.takeIf { it.isNotBlank() }?.let { qualityLabel(it) } ?: "未知音质")
    DownloadTask.STATUS_FAILED -> "失败"
    DownloadTask.STATUS_CANCELED -> "已取消"
    else -> task.status
}

private fun percent(task: DownloadTask): String {
    if (task.total <= 0) return ""
    return ((task.progress * 100 / task.total).coerceIn(0, 100)).toString() + "%"
}
