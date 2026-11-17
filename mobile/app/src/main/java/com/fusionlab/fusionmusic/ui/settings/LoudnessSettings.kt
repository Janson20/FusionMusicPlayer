package com.fusionlab.fusionmusic.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.core.loudness.LoudnessConstants
import java.util.Locale

@Composable
fun LoudnessSettings(container: AppContainer, revision: Long) {
    val config = container.config
    val service = container.loudnessService
    var refreshTick by remember { mutableStateOf(0) }
    val stats = remember(revision, refreshTick) { service.stats() }
    var target by remember(revision) { mutableFloatStateOf(config.getDouble("audio.target_lufs", -14.0).toFloat()) }
    var preamp by remember(revision) { mutableFloatStateOf(config.getDouble("audio.preamp_db", 0.0).toFloat()) }

    ExtraSwitchRow(
        "音量均衡",
        "按 EBU R128 测量响度并自动调整增益",
        config.getBoolean("audio.equalize", true)
    ) { config.setBoolean("audio.equalize", it) }
    Text(
        "目标响度 " + String.format(Locale.US, "%.1f", target) + " LUFS",
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(horizontal = 16.dp)
    )
    Slider(
        value = target,
        onValueChange = {
            target = it
            config.setDouble("audio.target_lufs", it.toDouble())
        },
        valueRange = -24f..-8f,
        modifier = Modifier.padding(horizontal = 12.dp)
    )
    Text(
        "预增益 " + String.format(Locale.US, "%+.1f", preamp) + " dB",
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(horizontal = 16.dp)
    )
    Slider(
        value = preamp,
        onValueChange = {
            preamp = it
            config.setDouble("audio.preamp_db", it.toDouble())
        },
        valueRange = -12f..12f,
        modifier = Modifier.padding(horizontal = 12.dp)
    )
    ExtraSwitchRow("允许抬升", "测出偏轻的曲目最多抬升 12 dB；关闭后只做衰减", config.getBoolean("audio.allow_boost", true)) {
        config.setBoolean("audio.allow_boost", it)
    }
    ExtraSwitchRow("预取下一首", "提前测量下一首，切歌时立即有增益", config.getBoolean("audio.prefetch_next", true)) {
        config.setBoolean("audio.prefetch_next", it)
    }
    ExtraSwitchRow("音源级兜底", "样本足够时用同音源中位增益估计测不出的曲目", config.getBoolean("audio.source_offset", true)) {
        config.setBoolean("audio.source_offset", it)
    }
    Text(
        "分析范围（秒，0 = 全曲）",
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
    )
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
        for (seconds in listOf(0, 30, 60, 90)) {
            ExtraChoiceChip(if (seconds == 0) "全曲" else seconds.toString() + "s", config.getInt("audio.analysis_seconds", 0) == seconds) {
                config.setInt("audio.analysis_seconds", seconds)
            }
        }
    }
    Text(
        "已测 " + stats.measured + " 首 · 失败 " + stats.failed + " 首 · 缓存 " + humanSize(stats.bytes) +
            (stats.avgLoudness?.let { " · 平均 " + String.format(Locale.US, "%.1f", it) + " LUFS" } ?: ""),
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 6.dp)
    )
    if (stats.analyzing.isNotBlank() || stats.pending > 0) {
        Text(
            "正在测量 " + stats.analyzing.ifBlank { stats.pending.toString() + " 首排队中" },
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(horizontal = 16.dp)
        )
    }
    Row(modifier = Modifier.padding(horizontal = 16.dp)) {
        TextButton(onClick = {
            service.clear()
            refreshTick++
        }) { Text("清空响度缓存") }
    }
}
