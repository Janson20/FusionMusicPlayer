package com.fusionlab.fusionmusic.ui.settings

import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import com.fusionlab.fusionmusic.core.loudness.LoudnessConstants
import com.fusionlab.fusionmusic.core.model.SourceRegistryMeta
import java.io.File
import java.util.Locale

@Composable
fun AppearanceSettings(container: AppContainer, revision: Long) {
    val context = LocalContext.current
    val config = container.config
    var imagePath by remember(revision) { mutableStateOf(config.getString("appearance.background_image", "")) }
    val scope = rememberCoroutineScope()
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val target = withContext(Dispatchers.IO) {
                val file = File(context.filesDir, "data/background.img").apply { parentFile?.mkdirs() }
                try {
                    context.contentResolver.openInputStream(uri)?.use { input ->
                        file.outputStream().use { output ->
                            val buffer = ByteArray(64 * 1024)
                            var total = 0L
                            while (true) {
                                val read = input.read(buffer)
                                if (read <= 0) break
                                total += read
                                if (total > 20L * 1024L * 1024L) {
                                    throw IllegalStateException("背景图不能超过 20 MB")
                                }
                                output.write(buffer, 0, read)
                            }
                        }
                    } ?: throw IllegalStateException("无法读取背景图")
                    file
                } catch (_: Exception) {
                    try {
                        file.delete()
                    } catch (_: Exception) {
                    }
                    null
                }
            }
            if (target != null) {
                imagePath = target.absolutePath
                config.setString("appearance.background_image", target.absolutePath)
                config.setString("appearance.background", "image")
            }
        }
    }
    ExtraSection("背景")
    Text(
        if (imagePath.isBlank()) "当前使用纯色背景" else "已选择本地背景图",
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 16.dp)
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)) {
        TextButton(onClick = { picker.launch(arrayOf("image/*")) }) { Text("选择图片") }
        TextButton(onClick = {
            try {
                File(context.filesDir, "data/background.img").delete()
            } catch (_: Exception) {
            }
            imagePath = ""
            config.setString("appearance.background_image", "")
            config.setString("appearance.background", "solid")
        }) { Text("清除背景图") }
    }
    val settings = listOf(
        Triple("背景不透明度", "appearance.background_opacity", 85),
        Triple("磨砂强度", "appearance.background_blur", 10),
        Triple("暗色蒙版", "appearance.background_scrim", 30),
        Triple("顶栏不透明度", "appearance.surface_overlay", 35),
        Triple("底栏不透明度", "appearance.surface_bottom", 40)
    )
    for ((label, key, fallback) in settings) {
        val value = config.getInt(key, fallback).coerceIn(0, 100)
        Text(
            label + " " + value + "%",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 6.dp)
        )
        Slider(
            value = value.toFloat(),
            onValueChange = { config.setInt(key, it.toInt().coerceIn(0, 100)) },
            valueRange = 0f..100f,
            modifier = Modifier.padding(horizontal = 12.dp)
        )
    }
}
