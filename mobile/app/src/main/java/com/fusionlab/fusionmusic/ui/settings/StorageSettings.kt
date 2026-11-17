package com.fusionlab.fusionmusic.ui.settings

import android.content.Intent
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.documentfile.provider.DocumentFile
import com.fusionlab.fusionmusic.AppContainer
import java.io.File
import java.util.Locale

@Composable
fun StorageSettings(container: AppContainer, revision: Long) {
    val context = LocalContext.current
    val config = container.config
    val dataDir = File(context.filesDir, "data")
    var refreshTick by remember { mutableStateOf(0) }
    val coverBytes = remember(revision, refreshTick) { directorySize(File(dataDir, "cache/cover")) }
    val lyricBytes = remember(revision, refreshTick) { directorySize(File(dataDir, "cache/lyric")) }
    val mediaBytes = remember(revision, refreshTick) { directorySize(File(dataDir, "cache/media")) }
    val downloadBytes = remember(revision, refreshTick) { directorySize(File(dataDir, "cache/downloads")) }
    val loudnessBytes = remember(revision, refreshTick) {
        val file = File(dataDir, "loudness.json")
        if (file.exists()) file.length() else 0L
    }
    var resetOpen by remember { mutableStateOf(false) }
    var downloadPath by remember(revision) { mutableStateOf(config.getString("storage.download_dir", "")) }
    val treePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocumentTree()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        try {
            context.contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION
            )
            downloadPath = uri.toString()
            config.setString("storage.download_dir", uri.toString())
        } catch (_: Exception) {
            // 某些文件提供方不支持持久授权；不写入半可用配置。
        }
    }

    if (resetOpen) {
        AlertDialog(
            onDismissRequest = { resetOpen = false },
            title = { Text("恢复默认设置") },
            text = { Text("会恢复主题、播放、音源、下载、歌词等设置；不会删除登录态、歌单和下载文件。") },
            confirmButton = {
                TextButton(onClick = {
                    config.resetAll()
                    resetOpen = false
                }) { Text("恢复默认") }
            },
            dismissButton = { TextButton(onClick = { resetOpen = false }) { Text("取消") } }
        )
    }

    ExtraSection("存储与缓存")
    Text(
        "封面 " + humanSize(coverBytes) + " · 歌词 " + humanSize(lyricBytes) +
            " · 音频 " + humanSize(mediaBytes),
        style = MaterialTheme.typography.bodySmall,
        modifier = Modifier.padding(horizontal = 16.dp)
    )
    Text(
        "下载临时文件 " + humanSize(downloadBytes) + " · 响度缓存 " + humanSize(loudnessBytes),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp)
    )
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 4.dp)
    ) {
        TextButton(onClick = {
            deleteDirectory(File(dataDir, "cache/cover"))
            deleteDirectory(File(dataDir, "cache/lyric"))
            refreshTick++
        }) { Text("清封面/歌词") }
        TextButton(onClick = {
            container.mediaCache.clear()
            refreshTick++
        }) { Text("清音频") }
        TextButton(onClick = {
            deleteDirectory(File(dataDir, "cache/downloads"))
            container.loudnessService.clear()
            refreshTick++
        }) { Text("清临时/响度") }
    }
    val limit = config.getInt("storage.media_cache_limit_mb", 2048).coerceIn(128, 8192)
    Text(
        "音频缓存上限 " + limit + " MB",
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
    )
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
        for (mb in listOf(512, 1024, 2048, 4096)) {
            ExtraChoiceChip(mb.toString(), limit == mb) {
                config.setInt("storage.media_cache_limit_mb", mb)
            }
        }
        TextButton(onClick = {
            container.mediaCache.trim(limit.toLong() * 1024L * 1024L)
            refreshTick++
        }) {
            Text("立即修剪")
        }
    }
    ExtraSwitchRow(
        "缓存歌词",
        "把翻译/罗马音/逐字歌词写入 cache/lyric",
        config.getBoolean("storage.cache_lyric", true)
    ) { config.setBoolean("storage.cache_lyric", it) }
    ExtraSwitchRow(
        "缓存音频",
        "需要请求头的音源无论如何都会缓存",
        config.getBoolean("storage.cache_media", false)
    ) { config.setBoolean("storage.cache_media", it) }

    ExtraSection("下载目录")
    Text(
        if (downloadPath.isBlank()) "系统媒体库 Music/FusionMusicPlayer" else displayTree(context, downloadPath),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp)
    )
    Text(
        "Android 10 及以上通过系统媒体库写入，不需要存储权限；Android 9 及以下拒绝写入权限时会退到应用专属外部目录。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp)
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
        TextButton(onClick = { treePicker.launch(null) }) { Text("选择目录") }
        TextButton(onClick = {
            downloadPath = ""
            config.setString("storage.download_dir", "")
        }) { Text("使用系统媒体库") }
    }

    ExtraSection("日志与重置")
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
        TextButton(onClick = {
            try {
                val uri = FileProvider.getUriForFile(
                    context,
                    context.packageName + ".fileprovider",
                    container.log.shareFile()
                )
                val send = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_STREAM, uri)
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                context.startActivity(Intent.createChooser(send, "分享日志"))
            } catch (_: Exception) {
                // 日志尚未生成或没有可分享的应用。
            }
        }) { Text("分享日志") }
        TextButton(onClick = { resetOpen = true }) { Text("恢复默认设置") }
    }
    Text(
        "数据目录：" + dataDir.absolutePath,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
    )
}

private fun displayTree(context: android.content.Context, value: String): String {
    return try {
        DocumentFile.fromTreeUri(context, Uri.parse(value))?.name ?: value
    } catch (_: Exception) {
        value
    }
}
