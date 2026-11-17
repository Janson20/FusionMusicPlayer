package com.fusionlab.fusionmusic.ui.account

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.outlined.CameraAlt
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.fusionlab.fusionmusic.AppContainer
import com.fusionlab.fusionmusic.data.account.DesktopLoginCandidate
import kotlinx.coroutines.launch

/**
 * 扫描电脑端生成的一次性二维码，把桌面登录态接到手机上。
 *
 * 只接受 App 内扫码。二维码里的自定义 scheme 不注册成系统深链，避免别的 App
 * 抢注同一个 scheme 后截走二维码里的临时密钥。
 */
@Composable
fun DesktopScanScreen(
    container: AppContainer,
    onBack: () -> Unit,
    onLoggedIn: () -> Unit
) {
    val context = LocalContext.current
    val account = container.account
    val state by account.snapshot.collectAsState()
    var granted by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)
    }
    var cameraError by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var errorText by remember { mutableStateOf<String?>(null) }
    var candidate by remember { mutableStateOf<DesktopLoginCandidate?>(null) }
    var confirmReplace by remember { mutableStateOf(false) }
    var scanKey by remember { mutableIntStateOf(0) }
    val scope = rememberCoroutineScope()
    val lifecycleOwner = LocalLifecycleOwner.current

    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { value ->
        granted = value
    }

    LaunchedEffect(Unit) {
        if (!granted) permissionLauncher.launch(Manifest.permission.CAMERA)
    }
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                granted = ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    BackHandler(enabled = busy) {
        // 验证中不退出，避免请求被取消后只导入了一半
    }

    suspend fun apply(candidateValue: DesktopLoginCandidate) {
        busy = true
        errorText = null
        val ok = account.applyDesktopLogin(candidateValue)
        busy = false
        if (ok) {
            onLoggedIn()
        } else {
            errorText = account.snapshot.value.error ?: "导入桌面登录失败，请重试"
            candidate = null
            scanKey += 1
        }
    }

    fun accept(uri: String) {
        if (busy || candidate != null) return
        busy = true
        errorText = null
        scope.launch {
            val parsed = account.prepareDesktopLogin(uri)
            if (parsed == null) {
                busy = false
                errorText = account.snapshot.value.error ?: "无法读取桌面登录信息"
                scanKey += 1
                return@launch
            }
            val sameAccount = state.userId != 0L && parsed.userId != 0L && state.userId == parsed.userId
            if (state.loggedIn && !sameAccount) {
                candidate = parsed
                confirmReplace = true
                busy = false
            } else {
                apply(parsed)
            }
        }
    }

    if (confirmReplace && candidate != null) {
        val incoming = candidate
        AlertDialog(
            onDismissRequest = {
                confirmReplace = false
                candidate = null
                scanKey += 1
            },
            title = { Text("替换手机上的登录账号？") },
            text = {
                Text(
                    "手机当前登录的是「" + (state.nickname.ifBlank { "其他账号" }) +
                        "」，电脑端二维码对应「" + (incoming?.nickname?.ifBlank { "网易云账号" } ?: "网易云账号") +
                        "」。继续会替换手机上的登录状态。"
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmReplace = false
                    val value = incoming ?: return@TextButton
                    candidate = null
                    scope.launch { apply(value) }
                }) { Text("替换并登录") }
            },
            dismissButton = {
                TextButton(onClick = {
                    confirmReplace = false
                    candidate = null
                    scanKey += 1
                }) { Text("取消") }
            }
        )
    }

    Column(
        modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(onClick = onBack, enabled = !busy) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("从电脑扫码", style = MaterialTheme.typography.titleLarge)
        }

        if (!granted) {
            Box(modifier = Modifier.weight(1f).fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Icon(Icons.Outlined.CameraAlt, contentDescription = null, modifier = Modifier.size(48.dp))
                    Text("需要相机权限", style = MaterialTheme.typography.titleMedium)
                    Text(
                        "扫描电脑上显示的登录二维码需要访问相机。App 不保存相机画面，也不会把画面上传。",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Button(onClick = { permissionLauncher.launch(Manifest.permission.CAMERA) }) {
                        Text("允许使用相机")
                    }
                    TextButton(onClick = { openAppSettings(context) }) { Text("打开系统设置") }
                }
            }
            return@Column
        }

        Box(modifier = Modifier.weight(1f).fillMaxWidth().background(Color.Black)) {
            QrCameraPreview(
                scanKey = scanKey,
                onQr = { accept(it) },
                onFailure = { cameraError = it }
            )
            Box(
                modifier = Modifier
                    .align(Alignment.Center)
                    .size(248.dp)
                    .border(2.dp, Color.White, RoundedCornerShape(18.dp))
            )
            Text(
                "将电脑上的二维码放入框内",
                color = Color.White,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 28.dp)
            )
            if (busy) {
                Box(
                    modifier = Modifier.fillMaxSize().background(Color(0x99000000)),
                    contentAlignment = Alignment.Center
                ) {
                    CircularProgressIndicator(color = Color.White)
                }
            }
        }

        val message = errorText ?: cameraError
        if (message != null) {
            Text(
                message,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.error,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
            )
            TextButton(
                onClick = {
                    errorText = null
                    cameraError = null
                    scanKey += 1
                },
                modifier = Modifier.padding(horizontal = 8.dp)
            ) { Text("重新扫描") }
        } else {
            Text(
                "请使用电脑上的「手机扫码登录」二维码。二维码 180 秒内有效，且只能使用一次。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp)
            )
        }
    }
}


private fun openAppSettings(context: Context) {
    try {
        context.startActivity(
            Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + context.packageName))
        )
    } catch (_: Exception) {
        // 设置页打不开时用户仍可手动去系统设置
    }
}
