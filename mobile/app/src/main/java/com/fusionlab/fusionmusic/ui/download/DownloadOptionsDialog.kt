package com.fusionlab.fusionmusic.ui.download

import android.widget.Toast
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.model.QualityLevel
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.model.qualityLabel

@Composable
fun DownloadOptionsDialog(
    track: Track,
    defaultQuality: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit
) {
    QualityDialog(
        title = "下载「" + track.name + "」",
        subtitle = "音源：" + track.sourceText + " · 可用音质：" +
            (track.qualityList.joinToString(" / ").ifBlank { "未知" }),
        defaultQuality = defaultQuality,
        onDismiss = onDismiss,
        onConfirm = onConfirm
    )
}

@Composable
fun BatchDownloadDialog(
    tracks: List<Track>,
    defaultQuality: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit
) {
    QualityDialog(
        title = "下载 " + tracks.size + " 首歌曲",
        subtitle = "按当前音源与设置的音质逐首下载；本地曲目会自动跳过。",
        defaultQuality = defaultQuality,
        onDismiss = onDismiss,
        onConfirm = onConfirm
    )
}

@Composable
fun BatchDownloadButton(container: AppContainer, tracks: List<Track>, label: String = "下载全部") {
    val context = LocalContext.current
    val candidates = tracks.filterNot { it.isLocal }
    var open by remember { mutableStateOf(false) }
    TextButton(
        enabled = candidates.isNotEmpty(),
        onClick = { open = true }
    ) { Text(label) }
    if (open) {
        BatchDownloadDialog(
            tracks = candidates,
            defaultQuality = container.config.getString("download.quality", "320k"),
            onDismiss = { open = false },
            onConfirm = { quality ->
                container.downloadRepository.enqueue(candidates, quality)
                open = false
                Toast.makeText(context, "已加入下载队列（" + candidates.size + " 首）", Toast.LENGTH_SHORT).show()
            }
        )
    }
}

@Composable
private fun QualityDialog(
    title: String,
    subtitle: String,
    defaultQuality: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit
) {
    val choices = remember { listOf(QualityLevel.AUTO) + QualityLevel.ALL }
    var selected by remember {
        mutableStateOf(if (choices.contains(defaultQuality)) defaultQuality else QualityLevel.MEDIUM)
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                for (choice in choices) {
                    Row(
                        modifier = Modifier.fillMaxWidth()
                            .selectable(selected = selected == choice, onClick = { selected = choice })
                            .padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        RadioButton(selected = selected == choice, onClick = { selected = choice })
                        Text(
                            if (choice == QualityLevel.AUTO) "自动（尽力取最高档）" else qualityLabel(choice),
                            modifier = Modifier.padding(start = 8.dp)
                        )
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(selected) }) { Text("开始下载") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } }
    )
}
