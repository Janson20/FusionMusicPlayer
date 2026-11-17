package com.fusionlab.fusionmusic.ui.account

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.fusionlab.fusionmusic.AppContainer
import com.google.zxing.BarcodeFormat
import com.google.zxing.EncodeHintType
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

@Composable
fun LoginScreen(container: AppContainer, onBack: () -> Unit) {
    val account = container.account
    val state by account.snapshot.collectAsState()
    val scope = rememberCoroutineScope()
    var tab by remember { mutableStateOf("qr") }
    var qrKey by remember { mutableStateOf<String?>(null) }
    var qrBitmap by remember { mutableStateOf<Bitmap?>(null) }
    var qrRunning by remember { mutableStateOf(false) }
    var phone by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }
    var countryCode by remember { mutableStateOf("86") }
    var usePassword by remember { mutableStateOf(false) }
    var cookie by remember { mutableStateOf("") }

    LaunchedEffect(qrRunning, qrKey) {
        val key = qrKey ?: return@LaunchedEffect
        while (isActive && qrRunning) {
            delay(1500)
            val check = account.pollQr(key) ?: continue
            if (check.code == 803) {
                qrRunning = false
                break
            }
            if (check.code == 800) {
                qrRunning = false
                qrKey = null
                qrBitmap = null
                break
            }
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.Outlined.ArrowBack, contentDescription = "返回")
            }
            Text("网易云账号", style = MaterialTheme.typography.titleLarge)
        }
        Text(
            state.status,
            style = MaterialTheme.typography.bodyMedium,
            color = if (state.error != null) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(vertical = 8.dp)
        )

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            FilterChip(selected = tab == "qr", onClick = { tab = "qr" }, label = { Text("扫码") })
            FilterChip(selected = tab == "phone", onClick = { tab = "phone" }, label = { Text("手机号") })
            FilterChip(selected = tab == "cookie", onClick = { tab = "cookie" }, label = { Text("Cookie") })
        }

        when (tab) {
            "qr" -> {
                Button(
                    onClick = {
                        scope.launch {
                            qrBitmap = null
                            qrKey = account.startQrLogin()
                            qrRunning = qrKey != null
                            val key = qrKey
                            if (key != null) qrBitmap = renderQr("https://music.163.com/login?codekey=" + key)
                        }
                    },
                    modifier = Modifier.padding(top = 16.dp)
                ) { Text(if (qrRunning) "重新获取二维码" else "获取二维码") }
                val bitmap = qrBitmap
                if (bitmap != null) {
                    Image(
                        bitmap = bitmap.asImageBitmap(),
                        contentDescription = "登录二维码",
                        modifier = Modifier.size(260.dp).padding(top = 16.dp)
                    )
                }
                Text(
                    "使用网易云音乐 App 扫描二维码并在手机上确认。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
            "phone" -> {
                OutlinedTextField(
                    value = phone,
                    onValueChange = { phone = it },
                    label = { Text("手机号") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp)
                )
                OutlinedTextField(
                    value = countryCode,
                    onValueChange = { countryCode = it },
                    label = { Text("国家/地区代码") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
                )
                OutlinedTextField(
                    value = secret,
                    onValueChange = { secret = it },
                    label = { Text(if (usePassword) "密码" else "短信验证码") },
                    singleLine = true,
                    visualTransformation = if (usePassword) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
                    modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
                )
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
                    Switch(checked = usePassword, onCheckedChange = { usePassword = it })
                    Text("使用密码登录", modifier = Modifier.padding(start = 8.dp))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.padding(top = 8.dp)) {
                    TextButton(onClick = { scope.launch { account.sendCaptcha(phone, countryCode) } }) {
                        Text("发送验证码")
                    }
                    Button(onClick = { scope.launch { account.loginWithPhone(phone, secret, countryCode, usePassword) } }) {
                        Text("登录")
                    }
                }
                Text(
                    "网易云已逐步下线密码登录，服务端返回 502 时请改用扫码或短信验证码。",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
            else -> {
                OutlinedTextField(
                    value = cookie,
                    onValueChange = { cookie = it },
                    label = { Text("粘贴 Cookie（需包含 MUSIC_U）") },
                    minLines = 4,
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp)
                )
                Button(
                    onClick = { scope.launch { account.loginWithCookie(cookie) } },
                    modifier = Modifier.padding(top = 12.dp)
                ) { Text("使用 Cookie 登录") }
            }
        }

        if (state.loggedIn) {
            Text(
                "当前账号：" + state.nickname + "  " + state.vipLabel,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(top = 24.dp)
            )
            TextButton(onClick = { scope.launch { account.logout() } }) { Text("退出登录") }
        }
    }
}

private fun renderQr(text: String): Bitmap? {
    return try {
        val matrix = QRCodeWriter().encode(
            text,
            BarcodeFormat.QR_CODE,
            512,
            512,
            mapOf(EncodeHintType.MARGIN to 1)
        )
        val bitmap = Bitmap.createBitmap(matrix.width, matrix.height, Bitmap.Config.ARGB_8888)
        for (x in 0 until matrix.width) {
            for (y in 0 until matrix.height) {
                bitmap.setPixel(x, y, if (matrix.get(x, y)) android.graphics.Color.BLACK else android.graphics.Color.WHITE)
            }
        }
        bitmap
    } catch (_: Exception) {
        null
    }
}
