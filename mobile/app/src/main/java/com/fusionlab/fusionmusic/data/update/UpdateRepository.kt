package com.fusionlab.fusionmusic.data.update

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInstaller
import androidx.core.app.NotificationCompat
import android.net.Uri
import android.os.Build
import android.provider.Settings
import com.fusionlab.fusionmusic.BuildConfig
import com.fusionlab.fusionmusic.MainActivity
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import java.io.File
import kotlin.math.max

enum class UpdatePhase {
    IDLE, CHECKING, UPTODATE, AVAILABLE, DOWNLOADING, READY, INSTALLING, FAILED
}

data class UpdateState(
    val phase: UpdatePhase = UpdatePhase.IDLE,
    val currentVersion: String = BuildConfig.APP_VERSION,
    val release: ReleaseInfo? = null,
    val asset: ReleaseAsset? = null,
    val file: File? = null,
    val progress: Long = 0L,
    val total: Long = 0L,
    val error: String = "",
    val message: String = "",
    val needsInstallPermission: Boolean = false,
    val canAutoInstall: Boolean = !BuildConfig.DEBUG
) {
    val busy: Boolean
        get() = phase == UpdatePhase.CHECKING || phase == UpdatePhase.DOWNLOADING || phase == UpdatePhase.INSTALLING
    val progressFraction: Float
        get() = if (total > 0) (progress.toFloat() / total).coerceIn(0f, 1f) else 0f
    val statusText: String
        get() = when (phase) {
            UpdatePhase.IDLE -> ""
            UpdatePhase.CHECKING -> "正在检查更新…"
            UpdatePhase.UPTODATE -> "已是最新版本（" + currentVersion + "）"
            UpdatePhase.AVAILABLE -> "发现新版本 " + (release?.version ?: "")
            UpdatePhase.DOWNLOADING -> "正在下载 " + (progressFraction * 100).toInt() + "%"
            UpdatePhase.READY -> "已下载完成，可以安装"
            UpdatePhase.INSTALLING -> "正在准备安装…"
            UpdatePhase.FAILED -> error.ifBlank { "更新失败" }
        }
}

class UpdateRepository(
    context: Context,
    private val config: ConfigRepository,
    private val log: AppLog,
    private val scope: CoroutineScope
) {
    private val appContext = context.applicationContext
    private val updatesDir = File(appContext.filesDir, "data/updates").apply { mkdirs() }
    private val stateFlow = MutableStateFlow(UpdateState())
    private val notificationManager = appContext.getSystemService(NotificationManager::class.java)
    init {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            notificationManager?.createNotificationChannel(
                NotificationChannel(UPDATE_CHANNEL, "应用更新", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
    }
    private var checkedThisRun = false
    @Volatile private var cancelRequested = false

    val state: StateFlow<UpdateState> = stateFlow
    val currentVersion: String = BuildConfig.APP_VERSION

    fun maybeAutoCheck() {
        if (checkedThisRun) return
        if (!config.getBoolean("update.auto_check", true)) return
        val interval = max(1, config.getInt("update.interval_hours", 24)) * 3600_000L
        val last = config.getLong("update.last_check", 0L)
        if (System.currentTimeMillis() - last < interval) return
        checkedThisRun = true
        check(silent = true)
    }

    fun check(silent: Boolean = false) {
        if (stateFlow.value.busy) return
        stateFlow.value = stateFlow.value.copy(
            phase = UpdatePhase.CHECKING,
            error = "",
            message = "",
            needsInstallPermission = false
        )
        scope.launch(Dispatchers.IO) {
            val includePre = config.getBoolean("update.include_prerelease", false)
            val timeout = config.getInt("advanced.timeout", 15).coerceIn(5, 60)
            val client = Updater.buildClient(timeout, config.getString("advanced.proxy", ""))
            val url = if (includePre) {
                Updater.GITHUB_API + "/repos/" + Updater.DEFAULT_REPO + "/releases?per_page=10"
            } else {
                Updater.GITHUB_API + "/repos/" + Updater.DEFAULT_REPO + "/releases/latest"
            }
            val text = try {
                client.newCall(Updater.apiRequest(url)).execute().use { response ->
                    if (!Updater.urlAllowed(response.request.url.toString())) {
                        fail("GitHub 请求被重定向到不允许的域名，已拒绝")
                        return@use null
                    }
                    if (response.code == 404) {
                        fail("找不到发布信息（仓库或版本可能有问题）")
                        return@use null
                    }
                    if (response.code == 403 && response.body?.string()?.contains("rate limit", ignoreCase = true) == true) {
                        fail("GitHub 接口访问次数已达上限，请稍后再试")
                        return@use null
                    }
                    if (!response.isSuccessful) {
                        fail("GitHub 返回错误：HTTP " + response.code)
                        return@use null
                    }
                    response.body?.string()
                }
            } catch (error: Exception) {
                fail("无法连接 GitHub：" + (error.message ?: error.javaClass.simpleName))
                null
            } ?: return@launch

            val release = if (includePre) Updater.parseLatestList(text) else Updater.parseLatest(text)
            config.setLong("update.last_check", System.currentTimeMillis())
            if (release == null) {
                fail("发布信息里没有可用的版本号")
                return@launch
            }
            if (!Updater.isNewer(release.version, currentVersion)) {
                stateFlow.value = stateFlow.value.copy(
                    phase = UpdatePhase.UPTODATE,
                    release = release,
                    asset = null,
                    message = ""
                )
                return@launch
            }
            val skipped = config.getString("update.skip_version", "")
            if (skipped == release.version) {
                stateFlow.value = stateFlow.value.copy(
                    phase = UpdatePhase.UPTODATE,
                    release = release,
                    asset = null,
                    message = "已跳过版本 " + release.version
                )
                return@launch
            }
            val asset = release.assetForAndroid()
            if (asset == null) {
                stateFlow.value = stateFlow.value.copy(
                    phase = UpdatePhase.AVAILABLE,
                    release = release,
                    asset = null,
                    error = "这个版本没有 Android APK，请到发布页手动下载"
                )
                return@launch
            }
            stateFlow.value = stateFlow.value.copy(
                phase = UpdatePhase.AVAILABLE,
                release = release,
                asset = asset,
                error = "",
                message = if (silent) "发现新版本 " + release.version else ""
            )
            if (silent) notifyAvailable(release)
        }
    }

    fun download() {
        val current = stateFlow.value
        if (current.phase != UpdatePhase.AVAILABLE && current.phase != UpdatePhase.FAILED) return
        val release = current.release ?: return
        val asset = current.asset ?: release.assetForAndroid() ?: run {
            fail("没有可下载的 Android APK")
            return
        }
        cancelRequested = false
        stateFlow.value = current.copy(
            phase = UpdatePhase.DOWNLOADING,
            asset = asset,
            error = "",
            progress = 0L,
            total = asset.size,
            message = ""
        )
        scope.launch(Dispatchers.IO) {
            try {
                val timeout = config.getInt("advanced.timeout", 15).coerceIn(5, 60)
                val client = Updater.buildClient(timeout, config.getString("advanced.proxy", ""))
                val expected = resolveChecksum(client, release, asset)
                val file = Updater.download(
                    client = client,
                    asset = asset,
                    expectedSha256 = expected,
                    targetDir = updatesDir,
                    shouldCancel = { cancelRequested },
                    onProgress = { done, total ->
                        stateFlow.value = stateFlow.value.copy(progress = done, total = total)
                    }
                )
                stateFlow.value = stateFlow.value.copy(
                    phase = UpdatePhase.READY,
                    file = file,
                    progress = file.length(),
                    total = file.length(),
                    error = "",
                    message = "已下载 " + file.name
                )
            } catch (error: Exception) {
                log.w("Update", "download failed: " + error.message)
                if (cancelRequested) {
                    stateFlow.value = stateFlow.value.copy(
                        phase = UpdatePhase.AVAILABLE,
                        error = "已取消下载",
                        progress = 0L,
                        total = 0L
                    )
                } else {
                    fail(error.message ?: "下载失败")
                }
            }
        }
    }

    fun install() {
        val current = stateFlow.value
        if (current.phase != UpdatePhase.READY) {
            fail("还没有下载好可安装的更新")
            return
        }
        if (BuildConfig.DEBUG) {
            fail("调试构建不支持应用内更新，请安装 release 包")
            return
        }
        val file = current.file
        if (file == null || !file.exists() || file.length() <= 0L) {
            fail("更新文件不存在，请重新下载")
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            !appContext.packageManager.canRequestPackageInstalls()
        ) {
            stateFlow.value = stateFlow.value.copy(
                needsInstallPermission = true,
                error = "需要允许安装未知来源应用"
            )
            return
        }
        try {
            val installer = appContext.packageManager.packageInstaller
            val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL)
            params.setAppPackageName(appContext.packageName)
            val sessionId = installer.createSession(params)
            installer.openSession(sessionId).use { session ->
                session.openWrite("base.apk", 0L, file.length()).use { output ->
                    file.inputStream().use { input -> input.copyTo(output) }
                    session.fsync(output)
                }
                val callback = Intent(appContext, UpdateInstallReceiver::class.java)
                    .setAction(UpdateInstallReceiver.ACTION_STATUS)
                    .putExtra(UpdateInstallReceiver.EXTRA_SESSION_ID, sessionId)
                val flags = PendingIntent.FLAG_UPDATE_CURRENT or
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) PendingIntent.FLAG_MUTABLE else 0
                val pending = PendingIntent.getBroadcast(appContext, sessionId, callback, flags)
                session.commit(pending.intentSender)
            }
            stateFlow.value = stateFlow.value.copy(phase = UpdatePhase.INSTALLING, error = "", message = "")
        } catch (error: Exception) {
            log.w("Update", "install failed: " + error.message)
            fail("无法启动安装：" + (error.message ?: error.javaClass.simpleName))
        }
    }

    fun openInstallPermission() {
        try {
            val intent = Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + appContext.packageName)
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            appContext.startActivity(intent)
        } catch (error: Exception) {
            fail("无法打开安装权限设置：" + (error.message ?: ""))
        }
    }

    fun openReleasePage() {
        val url = stateFlow.value.release?.htmlUrl
            ?.takeIf { it.isNotBlank() }
            ?: ("https://github.com/" + Updater.DEFAULT_REPO + "/releases")
        try {
            appContext.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        } catch (error: Exception) {
            fail("无法打开浏览器：" + url)
        }
    }

    fun skipCurrent() {
        val version = stateFlow.value.release?.version ?: return
        config.setString("update.skip_version", version)
        stateFlow.value = stateFlow.value.copy(
            phase = UpdatePhase.UPTODATE,
            message = "已跳过版本 " + version
        )
    }

    fun cancelDownload() {
        if (stateFlow.value.phase == UpdatePhase.DOWNLOADING) {
            cancelRequested = true
        }
    }

    fun onInstallResult(status: Int, message: String) {
        when (status) {
            PackageInstaller.STATUS_SUCCESS -> {
                stateFlow.value = stateFlow.value.copy(
                    phase = UpdatePhase.INSTALLING,
                    error = "",
                    message = "安装完成，正在重启应用"
                )
            }
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                stateFlow.value = stateFlow.value.copy(message = "等待系统确认安装")
            }
            else -> fail(message.ifBlank { "安装失败（状态 " + status + "）" })
        }
        log.i("Update", "install status=" + status + " " + message)
    }

    fun clearError() {
        if (stateFlow.value.phase == UpdatePhase.FAILED) {
            stateFlow.value = stateFlow.value.copy(phase = UpdatePhase.IDLE, error = "")
        }
    }

    private fun resolveChecksum(client: okhttp3.OkHttpClient, release: ReleaseInfo, asset: ReleaseAsset): String {
        val direct = asset.sha256
        if (direct.isNotBlank()) return direct
        val checksumAsset = release.checksumFor(asset)
            ?: throw IllegalStateException("发布信息没有提供 SHA-256 校验，已放弃自动更新")
        if (!Updater.urlAllowed(checksumAsset.url)) {
            throw IllegalStateException("校验文件地址不在允许的域名内，已拒绝")
        }
        val text = client.newCall(
            okhttp3.Request.Builder().url(checksumAsset.url)
                .header("User-Agent", Updater.USER_AGENT)
                .build()
        ).execute().use { response ->
            if (!Updater.urlAllowed(response.request.url.toString())) {
                throw IllegalStateException("校验文件被重定向到不允许的域名，已拒绝")
            }
            if (!response.isSuccessful) throw IllegalStateException("下载校验文件失败：HTTP " + response.code)
            response.body?.string()
        } ?: throw IllegalStateException("校验文件为空")
        return Updater.parseChecksum(text)
            ?: throw IllegalStateException("校验文件格式不正确，已放弃自动更新")
    }

    private fun notifyAvailable(release: ReleaseInfo) {
        try {
            val intent = Intent(appContext, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            val pending = PendingIntent.getActivity(
                appContext,
                7001,
                intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            val notification = NotificationCompat.Builder(appContext, UPDATE_CHANNEL)
                .setSmallIcon(com.fusionlab.fusionmusic.R.drawable.ic_stat_fusion)
                .setContentTitle("发现 Fusion Music " + release.version)
                .setContentText("打开设置页可以下载并安装更新")
                .setContentIntent(pending)
                .setAutoCancel(true)
                .setOnlyAlertOnce(true)
                .build()
            notificationManager?.notify(UPDATE_NOTIFICATION_ID, notification)
        } catch (_: Exception) {
            // 通知权限缺失或系统限制时，设置页仍能看到更新状态。
        }
    }

    private fun fail(message: String) {
        stateFlow.value = stateFlow.value.copy(
            phase = UpdatePhase.FAILED,
            error = message,
            message = ""
        )
    }

    companion object {
        private const val UPDATE_CHANNEL = "fusion_updates"
        private const val UPDATE_NOTIFICATION_ID = 7001

        fun humanSize(bytes: Long): String {
            if (bytes <= 0L) return "未知大小"
            if (bytes < 1024L) return bytes.toString() + " B"
            if (bytes < 1024L * 1024L) return String.format(java.util.Locale.US, "%.0f KB", bytes / 1024.0)
            return String.format(java.util.Locale.US, "%.1f MB", bytes / (1024.0 * 1024.0))
        }
    }
}
