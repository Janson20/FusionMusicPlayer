package com.fusionlab.fusionmusic.ui.settings

import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.BuildConfig
import com.fusionlab.fusionmusic.core.model.QualityLevel
import com.fusionlab.fusionmusic.core.model.SourceRegistryMeta
import com.fusionlab.fusionmusic.core.model.qualityLabel
import com.fusionlab.fusionmusic.playback.PlaybackController
import com.fusionlab.fusionmusic.playback.PlaybackService
import kotlinx.coroutines.launch

private val ACCENTS = listOf("#6C4DF6", "#3B82F6", "#0EA5A4", "#E5484D", "#F59E0B", "#EC4899")

@Composable
fun SettingsScreen(
    container: AppContainer,
    onBack: () -> Unit,
    onLogin: () -> Unit,
    onDesktopScan: () -> Unit
) {
    val context = LocalContext.current
    val config = container.config
    val revision by config.revisions.collectAsState()
    val account = container.account
    val accountState by account.snapshot.collectAsState()
    var confirmRebuild by remember { mutableStateOf(false) }
    var proxyText by remember(revision) { mutableStateOf(config.getString("advanced.proxy", "")) }
    var timeoutText by remember(revision) { mutableStateOf(config.getInt("advanced.timeout", 15).toString()) }
    var templateText by remember(revision) { mutableStateOf(config.getString("download.filename_template", "{singer} - {name}")) }
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current
    var notificationsEnabled by remember {
        mutableStateOf(mediaNotificationsEnabled(context))
    }
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                notificationsEnabled = mediaNotificationsEnabled(context)
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    if (confirmRebuild) {
        AlertDialog(
            onDismissRequest = { confirmRebuild = false },
            title = { Text("重建凭据密钥") },
            text = { Text("旧密钥会改名为 master.key.unreadable 留档，已保存的登录状态将作废，需要重新登录。") },
            confirmButton = {
                TextButton(onClick = {
                    account.rebuildKey()
                    confirmRebuild = false
                }) { Text("确认重建") }
            },
            dismissButton = { TextButton(onClick = { confirmRebuild = false }) { Text("取消") } }
        )
    }

    Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        Row(modifier = Modifier.fillMaxWidth().padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("设置", style = MaterialTheme.typography.titleLarge)
        }

        Section("账号")
        Text(
            accountState.status + if (accountState.nickname.isNotBlank()) " · " + accountState.nickname else "",
            style = MaterialTheme.typography.bodyMedium,
            color = if (accountState.error != null) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
        )
        if (accountState.loggedIn) {
            Text(accountState.vipLabel + "  " + accountState.vipDetail, style = MaterialTheme.typography.bodySmall)
            Text(
                "凭据剩余 " + accountState.daysLeft + " 天 · 密钥来源：" + accountState.keySource,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Text(
                "远程歌单 " + accountState.remotePlaylists.size + " 个",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 8.dp)) {
                Button(onClick = onDesktopScan) { Text("手机扫码") }
                TextButton(onClick = { scope.launch { account.logout() } }) { Text("退出登录") }
            }
        } else {
            Button(onClick = onLogin, modifier = Modifier.padding(top = 8.dp)) { Text("登录网易云") }
        }
        SwitchRow(
            title = "便携密钥",
            subtitle = if (accountState.portable) "密钥文件可随数据目录迁移" else "密钥绑定 Android Keystore",
            checked = accountState.portable,
            onChange = { account.setPortable(it) }
        )
        TextButton(onClick = { confirmRebuild = true }) { Text("重建密钥并重新登录") }

        Section("外观")
        Text("主题", style = MaterialTheme.typography.bodyMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ChoiceChip("跟随系统", config.getString("appearance.theme", "auto") == "auto") {
                config.setString("appearance.theme", "auto")
            }
            ChoiceChip("浅色", config.getString("appearance.theme") == "light") {
                config.setString("appearance.theme", "light")
            }
            ChoiceChip("深色", config.getString("appearance.theme") == "dark") {
                config.setString("appearance.theme", "dark")
            }
        }
        Text("强调色", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (accent in ACCENTS) {
                val selected = config.getString("appearance.accent", "#6C4DF6").equals(accent, ignoreCase = true)
                ChoiceChip(accent, selected) { config.setString("appearance.accent", accent) }
            }
        }
        AppearanceSettings(container, revision)

        Section("播放")
        Text("音质上限", style = MaterialTheme.typography.bodyMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            ChoiceChip("自动", config.getString("playback.quality", "320k") == "auto") {
                config.setString("playback.quality", "auto")
            }
            for (quality in QualityLevel.ALL) {
                ChoiceChip(qualityLabel(quality), config.getString("playback.quality") == quality) {
                    config.setString("playback.quality", quality)
                }
            }
        }
        Text("音量 " + config.getInt("playback.volume", 65) + "%", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 8.dp))
        Slider(
            value = config.getInt("playback.volume", 65).toFloat(),
            onValueChange = {
                val value = it.toInt().coerceIn(0, 100)
                config.setInt("playback.volume", value)
                PlaybackController.setVolume(context, value)
            },
            valueRange = 0f..100f
        )
        SwitchRow("跨音源兜底", "当前音源不可用时自动换源", config.getBoolean("sources.fallback", true)) {
            config.setBoolean("sources.fallback", it)
        }
        SwitchRow("启动时恢复上次播放", "恢复队列与进度，但不自动出声", config.getBoolean("playback.restore_session", true)) {
            config.setBoolean("playback.restore_session", it)
        }
        SwitchRow("自动播放下一首", "顺序模式播到末尾时停止", config.getBoolean("playback.auto_play_next", true)) {
            config.setBoolean("playback.auto_play_next", it)
        }
        SwitchRow("优先原唱", "搜索/兜底时优先原唱版本", config.getBoolean("sources.prefer_original", true)) {
            config.setBoolean("sources.prefer_original", it)
        }
        SwitchRow("缓存音频", "需要请求头的音源无论如何都会缓存", config.getBoolean("storage.cache_media", false)) {
            config.setBoolean("storage.cache_media", it)
        }
        SwitchRow("记住播放进度", "重启后从上一次的进度继续", config.getBoolean("playback.remember_progress", true)) {
            config.setBoolean("playback.remember_progress", it)
        }
        Text(
            "快进/快退步长",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 6.dp)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
            for (seconds in listOf(3, 5, 10, 15)) {
                ChoiceChip(seconds.toString() + " 秒", config.getInt("playback.seek_step_ms", 5000) == seconds * 1000) {
                    config.setInt("playback.seek_step_ms", seconds * 1000)
                }
            }
        }

        Text(
            "切歌淡入",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 6.dp)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
            for (ms in listOf(0, 300, 500, 1000)) {
                ChoiceChip(if (ms == 0) "关闭" else (ms / 1000.0).toString() + " 秒", config.getInt("playback.fade_in_ms", 0) == ms) {
                    config.setInt("playback.fade_in_ms", ms)
                }
            }
        }

        LoudnessSettings(container, revision)

        Section("通知")
        Text("媒体控制", style = MaterialTheme.typography.bodyMedium)
        Text(
            if (notificationsEnabled) {
                "通知已开启，播放时会在通知栏和锁屏显示上一首、播放/暂停、下一首。"
            } else {
                "通知已关闭，媒体控制不会显示。请允许 Fusion Music 发送通知。"
            },
            style = MaterialTheme.typography.bodySmall,
            color = if (notificationsEnabled) {
                MaterialTheme.colorScheme.onSurfaceVariant
            } else {
                MaterialTheme.colorScheme.error
            }
        )
        TextButton(onClick = {
            try {
                val intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
                    .putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)
                context.startActivity(intent)
            } catch (_: Exception) {
                val fallback = Intent(
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + context.packageName)
                )
                context.startActivity(fallback)
            }
        }) { Text("打开系统通知设置") }

        Section("音源")
        for (meta in SourceRegistryMeta.SOURCE_META) {
            val enabled = config.getStringList("sources.enabled").contains(meta.id)
            SwitchRow(meta.name, if (meta.id == "bili") "默认只参与跨源兜底" else "参与搜索与播放", enabled) { checked ->
                val current = config.getStringList("sources.enabled").toMutableList()
                if (checked && !current.contains(meta.id)) current.add(meta.id)
                if (!checked) current.remove(meta.id)
                if (current.isEmpty()) return@SwitchRow
                config.setStringList("sources.enabled", current)
            }
        }
        Text(
            "音源优先级",
            style = MaterialTheme.typography.titleSmall,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 10.dp)
        )
        SourcePrioritySettings(container, revision)

        Section("歌词")
        SwitchRow("显示翻译", "网易云 tlyric", config.getBoolean("lyrics.show_translation", true)) {
            config.setBoolean("lyrics.show_translation", it)
        }
        SwitchRow("显示罗马音", "网易云 romalrc", config.getBoolean("lyrics.show_romaji", false)) {
            config.setBoolean("lyrics.show_romaji", it)
        }
        SwitchRow("逐字歌词", "无真逐字时使用伪动态", config.getBoolean("lyrics.dynamic", true)) {
            config.setBoolean("lyrics.dynamic", it)
        }
        Text(
            "歌词字号 " + config.getInt("lyrics.font_size", 17) + "sp",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 6.dp)
        )
        Slider(
            value = config.getInt("lyrics.font_size", 17).toFloat(),
            onValueChange = { config.setInt("lyrics.font_size", it.toInt().coerceIn(12, 26)) },
            valueRange = 12f..26f,
            modifier = Modifier.padding(horizontal = 12.dp)
        )
        Text(
            "歌词对齐",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 4.dp)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
            ChoiceChip("左", config.getString("lyrics.alignment", "center") == "left") {
                config.setString("lyrics.alignment", "left")
            }
            ChoiceChip("中", config.getString("lyrics.alignment", "center") == "center") {
                config.setString("lyrics.alignment", "center")
            }
            ChoiceChip("右", config.getString("lyrics.alignment", "center") == "right") {
                config.setString("lyrics.alignment", "right")
            }
        }

        Section("下载")
        Text("下载音质", style = MaterialTheme.typography.bodyMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for (quality in QualityLevel.ALL) {
                ChoiceChip(qualityLabel(quality), config.getString("download.quality", "320k") == quality) {
                    config.setString("download.quality", quality)
                }
            }
        }
        OutlinedTextField(
            value = templateText,
            onValueChange = {
                templateText = it
                config.setString("download.filename_template", it)
            },
            label = { Text("文件名模板（{singer} / {name} / {album}）") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp)
        )
        SwitchRow("写入标签", "标题、歌手、专辑与年份", config.getBoolean("download.write_tags", true)) {
            config.setBoolean("download.write_tags", it)
        }
        SwitchRow("内嵌封面", "把封面写入音频标签", config.getBoolean("download.embed_cover", true)) {
            config.setBoolean("download.embed_cover", it)
        }
        SwitchRow("保存歌词", "在同目录写入 .lrc", config.getBoolean("download.save_lyric", true)) {
            config.setBoolean("download.save_lyric", it)
        }
        SwitchRow("加入本地曲库", "下载完成后加入本地音乐列表", config.getBoolean("download.add_to_library", false)) {
            config.setBoolean("download.add_to_library", it)
        }
        Text(
            "同名文件",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 6.dp)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
            ChoiceChip("重命名", config.getString("download.duplicate", "rename") == "rename") {
                config.setString("download.duplicate", "rename")
            }
            ChoiceChip("跳过", config.getString("download.duplicate", "rename") == "skip") {
                config.setString("download.duplicate", "skip")
            }
            ChoiceChip("覆盖", config.getString("download.duplicate", "rename") == "overwrite") {
                config.setString("download.duplicate", "overwrite")
            }
        }
        Text(
            "并发下载 " + config.getInt("download.concurrency", 2) + " 个",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 4.dp)
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.padding(horizontal = 16.dp)) {
            for (count in listOf(1, 2, 3, 4)) {
                ChoiceChip(count.toString(), config.getInt("download.concurrency", 2) == count) {
                    config.setInt("download.concurrency", count)
                }
            }
        }

        StorageSettings(container, revision)

        Section("高级")
        OutlinedTextField(
            value = proxyText,
            onValueChange = { proxyText = it },
            label = { Text("HTTP 代理，例如 127.0.0.1:7890") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
            OutlinedTextField(
                value = timeoutText,
                onValueChange = { timeoutText = it },
                label = { Text("超时（秒）") },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            TextButton(onClick = {
                config.setString("advanced.proxy", proxyText.trim())
                config.setInt("advanced.timeout", (timeoutText.toIntOrNull() ?: 15).coerceIn(5, 60))
                container.sourceRegistry.resetInstances()
            }) { Text("保存") }
        }
        Text(
            "保存后立即重建各音源实例，后续请求使用新代理与超时。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        UpdateSettings(container)

        Section("关于")
        Text("Fusion Music", style = MaterialTheme.typography.bodyLarge)
        Text("版本 " + BuildConfig.APP_VERSION, style = MaterialTheme.typography.bodySmall)
        Text(
            "Android 原生移植 · Kotlin / Compose / Media3",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 8.dp, bottom = 24.dp)
        )
    }
}

private fun mediaNotificationsEnabled(context: Context): Boolean {
    if (!NotificationManagerCompat.from(context).areNotificationsEnabled()) return false
    val channel = context.getSystemService(NotificationManager::class.java)
        ?.getNotificationChannel(PlaybackService.PLAYBACK_CHANNEL_ID)
    return channel == null || channel.importance != NotificationManager.IMPORTANCE_NONE
}

@Composable
private fun Section(title: String) {
    Text(
        title,
        style = MaterialTheme.typography.titleMedium,
        modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 20.dp, bottom = 6.dp)
    )
}

@Composable
private fun SwitchRow(
    title: String,
    subtitle: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyMedium)
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
private fun ChoiceChip(label: String, selected: Boolean, onClick: () -> Unit) {
    FilterChip(selected = selected, onClick = onClick, label = { Text(label) })
}


