package com.fusionlab.fusionmusic.ui.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.data.update.UpdatePhase
import com.fusionlab.fusionmusic.data.update.UpdateRepository

@Composable
fun UpdateSettings(container: AppContainer) {
    val config = container.config
    val repository = container.updateRepository
    val state by repository.state.collectAsState()
    val release = state.release

    ExtraSection("更新")
    Text(
        "当前版本 " + state.currentVersion + (if (state.canAutoInstall) "" else "（调试构建不支持应用内安装）"),
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(horizontal = 16.dp)
    )
    if (state.statusText.isNotBlank()) {
        Text(
            state.statusText,
            style = MaterialTheme.typography.bodySmall,
            color = if (state.phase == UpdatePhase.FAILED) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp)
        )
    }
    if (state.phase == UpdatePhase.DOWNLOADING) {
        LinearProgressIndicator(
            progress = { state.progressFraction },
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)
        )
        Text(
            UpdateRepository.humanSize(state.progress) + " / " + UpdateRepository.humanSize(state.total),
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 16.dp)
        )
    }
    if (release != null && state.phase != UpdatePhase.UPTODATE) {
        Text(
            "最新版本 " + release.version + (if (release.prerelease) "（预发布）" else ""),
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp)
        )
        if (release.body.isNotBlank()) {
            Text(
                com.fusionlab.fusionmusic.data.update.Updater.releaseNotesExcerpt(release.body),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 8,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
            )
        }
    }
    Row(
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 2.dp)
    ) {
        TextButton(enabled = !state.busy, onClick = { repository.check() }) { Text("检查更新") }
        when {
            state.phase == UpdatePhase.AVAILABLE || state.phase == UpdatePhase.FAILED -> {
                TextButton(onClick = { repository.download() }) { Text("下载") }
            }
            state.phase == UpdatePhase.DOWNLOADING -> {
                TextButton(onClick = { repository.cancelDownload() }) { Text("取消") }
            }
            state.phase == UpdatePhase.READY -> {
                TextButton(onClick = { repository.install() }) { Text("安装") }
            }
        }
        if (state.needsInstallPermission) {
            TextButton(onClick = { repository.openInstallPermission() }) { Text("允许安装") }
        }
        if (state.phase == UpdatePhase.AVAILABLE) {
            TextButton(onClick = { repository.skipCurrent() }) { Text("跳过此版本") }
        }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.padding(horizontal = 12.dp)) {
        TextButton(onClick = { repository.openReleasePage() }) { Text("打开发布页") }
        if (state.error.isNotBlank() && state.phase == UpdatePhase.FAILED) {
            TextButton(onClick = { repository.clearError() }) { Text("清除错误") }
        }
    }
    ExtraSwitchRow(
        "自动检查",
        "启动后按间隔在后台检查 GitHub Releases",
        config.getBoolean("update.auto_check", true)
    ) { config.setBoolean("update.auto_check", it) }
    ExtraSwitchRow(
        "包含预发布",
        "预发布版本默认不推荐给普通用户",
        config.getBoolean("update.include_prerelease", false)
    ) { config.setBoolean("update.include_prerelease", it) }
    Text(
        "检查间隔",
        style = MaterialTheme.typography.bodyMedium,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 2.dp)
    )
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
        for (hours in listOf(6, 24, 72, 168)) {
            val label = when (hours) {
                6 -> "6 小时"
                24 -> "每天"
                72 -> "3 天"
                else -> "每周"
            }
            ExtraChoiceChip(label, config.getInt("update.interval_hours", 24) == hours) {
                config.setInt("update.interval_hours", hours)
            }
        }
    }
    Text(
        "下载完成后必须通过服务端 SHA-256 校验才允许安装；校验文件缺失时不会自动安装。",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
    )
}
