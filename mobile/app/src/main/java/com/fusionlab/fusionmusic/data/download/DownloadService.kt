package com.fusionlab.fusionmusic.data.download

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import com.fusionlab.fusionmusic.FusionApplication
import com.fusionlab.fusionmusic.MainActivity
import com.fusionlab.fusionmusic.core.model.QualityLevel
import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.model.qualityLadder
import com.fusionlab.fusionmusic.core.util.AudioSniffer
import com.fusionlab.fusionmusic.core.util.Naming
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancel
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

class DownloadService : android.app.Service() {
    private lateinit var container: com.fusionlab.fusionmusic.AppContainer
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var worker: Job? = null
    private var progressJob: Job? = null
    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    override fun onCreate() {
        super.onCreate()
        container = (application as FusionApplication).container
        createChannel()
        startForegroundCompat(buildNotification("正在准备下载…", 0, 0, true))
        progressJob = scope.launch {
            while (isActive) {
                updateNotification()
                kotlinx.coroutines.delay(700)
            }
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startWorker()
        return START_STICKY
    }

    override fun onBind(intent: Intent?): android.os.IBinder? = null

    override fun onDestroy() {
        worker?.cancel()
        progressJob?.cancel()
        scope.cancel()
        super.onDestroy()
    }

    private fun startWorker() {
        if (worker?.isActive == true) return
        worker = scope.launch {
            val repository = container.downloadRepository
            val concurrency = container.config.getInt("download.concurrency", 2).coerceIn(1, 6)
            while (isActive) {
                val queued = repository.nextQueued(concurrency)
                if (queued.isEmpty()) break
                for (task in queued) repository.markRunning(task.id)
                updateNotification()
                coroutineScope {
                    queued.map { task ->
                        async(Dispatchers.IO) { process(task) }
                    }.awaitAll()
                }
                updateNotification()
            }
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun process(task: DownloadTask) {
        val repository = container.downloadRepository
        if (repository.taskById(task.id)?.status != DownloadTask.STATUS_RUNNING) return
        val tempDir = File(filesDir, "data/cache/downloads").apply { mkdirs() }
        val temp = File(tempDir, task.id + ".part")
        var actualQuality = task.quality
        var downloaded: Downloaded? = null
        try {
            val source = container.sourceRegistry.getSource(task.track.source)
                ?: throw IllegalStateException("音源不可用")
            for (quality in qualityLadder(task.quality)) {
                if (repository.taskById(task.id)?.status == DownloadTask.STATUS_CANCELED) return
                val url = try {
                    source.getMusicUrl(task.track.toMusicInfo(), quality)
                } catch (_: Exception) {
                    null
                } ?: continue
                repository.updateProgress(task.id, 0L, 0L)
                val headers = container.sourceRegistry.downloadHeaders(task.track.source)
                val cookies = container.sourceRegistry.downloadCookies(task.track.source)
                val result = download(url, headers, cookies, temp, task.id) ?: continue
                if (!AudioSniffer.isAudioFile(temp)) {
                    temp.delete()
                    continue
                }
                val seconds = AudioSniffer.probeFileDuration(temp.absolutePath)
                if (!AudioSniffer.durationMatches(task.track.interval, seconds)) {
                    temp.delete()
                    continue
                }
                val suffix = AudioSniffer.sniffSuffix(readHead(temp, 16)).ifBlank { ".mp3" }
                actualQuality = quality
                downloaded = Downloaded(temp, suffix, result)
                break
            }
            val result = downloaded ?: throw IllegalStateException("下载失败：所有音质档位均不可用")
            val template = container.config.getString("download.filename_template", "{singer} - {name}")
            val stem = Naming.suggestedStem(task.track, template)
            if (container.config.getBoolean("download.write_tags", true)) {
                val cover = if (container.config.getBoolean("download.embed_cover", true)) fetchCover(task.track) else null
                TagWriter.write(result.file, task.track, cover, container.log)
            }
            val published = DownloadPublisher.publish(
                context = this,
                source = result.file,
                displayStem = stem,
                suffix = result.suffix,
                duplicate = container.config.getString("download.duplicate", "rename"),
                downloadDir = container.config.getString("storage.download_dir", "")
            )
            if (published.skipped) {
                repository.markSkipped(task.id, "同名文件已存在，已跳过")
                result.file.delete()
                return
            }
            if (published.uri == null) {
                throw IllegalStateException(published.message.ifBlank { "写入下载目录失败" })
            }
            if (container.config.getBoolean("download.save_lyric", true)) {
                try {
                    val lyric = fetchLyric(task.track)
                    if (!lyric.isNullOrBlank()) {
                        val lyricPath = DownloadPublisher.writeLyric(
                            context = this,
                            audioStem = stem,
                            lyric = lyric,
                            downloadDir = container.config.getString("storage.download_dir", "")
                        )
                        if (lyricPath.isNullOrBlank()) {
                            container.log.w("DownloadService", "lyric not saved for " + task.track.name)
                        }
                    }
                } catch (error: Exception) {
                    // Lyrics are optional; a failure must not turn a completed
                    // audio download into a failed task.
                    container.log.w("DownloadService", "lyric save failed: " + error.message)
                }
            }
            container.log.i("DownloadService", "saved " + task.track.name + " -> " + published.path)
            repository.markDone(task.id, published.path, actualQuality, published.message)
            if (container.config.getBoolean("download.add_to_library", false)) {
                val local = Track(
                    source = Track.LOCAL_SOURCE,
                    songmid = published.path,
                    name = task.track.name,
                    singer = task.track.singer,
                    album = task.track.album,
                    interval = task.track.interval,
                    cover = task.track.cover,
                    path = published.path,
                    matchSource = task.track.source,
                    matchSongmid = task.track.songmid,
                    addedAt = System.currentTimeMillis()
                )
                container.library.addLocalTrack(local)
                container.localRepository.refreshTracks()
            }
            result.file.delete()
        } catch (error: Exception) {
            container.log.e("DownloadService", "task " + task.id + " failed: " + task.track.name, error)
            if (repository.taskById(task.id)?.status != DownloadTask.STATUS_CANCELED) {
                repository.markFailed(task.id, error.message ?: "下载失败")
            }
            temp.delete()
        }
    }

    private fun download(
        url: String,
        headers: Map<String, String>,
        cookies: Map<String, String>,
        target: File,
        taskId: String
    ): Long? {
        val builder = Request.Builder().url(url)
        for ((name, value) in headers) builder.header(name, value)
        if (cookies.isNotEmpty()) {
            builder.header("Cookie", cookies.entries.joinToString("; ") { it.key + "=" + it.value })
        }
        return try {
            client.newCall(builder.build()).execute().use { response ->
                if (!response.isSuccessful) return null
                val body = response.body ?: return null
                val total = body.contentLength()
                FileOutputStream(target).use { output ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(64 * 1024)
                        var written = 0L
                        var lastTick = SystemClock.elapsedRealtime()
                        var lastWritten = 0L
                        while (true) {
                            if (container.downloadRepository.taskById(taskId)?.status == DownloadTask.STATUS_CANCELED) {
                                target.delete()
                                return null
                            }
                            val count = input.read(buffer)
                            if (count <= 0) break
                            output.write(buffer, 0, count)
                            written += count
                            val now = SystemClock.elapsedRealtime()
                            if (now - lastTick >= 250) {
                                val speed = ((written - lastWritten) * 1000L) / (now - lastTick).coerceAtLeast(1L)
                                container.downloadRepository.updateProgress(taskId, written, total, speed)
                                lastTick = now
                                lastWritten = written
                            }
                        }
                        output.fd.sync()
                        container.downloadRepository.updateProgress(taskId, written, if (total > 0) total else written, 0)
                    }
                }
                body.contentLength().takeIf { it > 0 }
            }
        } catch (error: Exception) {
            target.delete()
            container.log.w("DownloadService", "download failed: " + error.message)
            null
        }
    }

    private fun fetchCover(track: Track): ByteArray? {
        val url = track.cover
        if (url.isBlank() || !url.startsWith("http")) return null
        return try {
            client.newCall(Request.Builder().url(url).build()).execute().use { response ->
                if (!response.isSuccessful) return null
                val bytes = response.body?.bytes() ?: return null
                if (bytes.size > 2 * 1024 * 1024) null else bytes
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun fetchLyric(track: Track): String? {
        val sourceId = track.source
        val info = track.toMusicInfo()
        return try {
            if (sourceId == "wy") {
                val source = container.sourceRegistry.getSource("wy") as? NeteaseSource
                val extras = source?.let { com.fusionlab.fusionmusic.data.source.NeteaseExtras(it) }
                extras?.fetchLyricBundle(track.songmid, wantTranslation = false, wantRoma = false, wantWord = false)?.lrc
            } else {
                container.sourceRegistry.getLyric(info, sourceId)
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun updateNotification() {
        val tasks = container.downloadRepository.tasks.value
        val active = tasks.count { it.status == DownloadTask.STATUS_RUNNING || it.status == DownloadTask.STATUS_QUEUED }
        val done = tasks.count { it.status == DownloadTask.STATUS_DONE }
        if (active == 0) return
        val running = tasks.firstOrNull { it.status == DownloadTask.STATUS_RUNNING }
        val progress = running?.progress ?: 0L
        val total = running?.total ?: 0L
        val text = if (running != null) {
            running.track.name + "  " + (if (total > 0) (progress * 100 / total).coerceIn(0, 100).toString() + "%" else "下载中")
        } else {
            "等待下载"
        }
        val notification = buildNotification(text, progress, total, active > 0)
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, notification)
    }

    private fun buildNotification(text: String, progress: Long, total: Long, indeterminate: Boolean): Notification {
        val intent = Intent(this, MainActivity::class.java)
        val pending = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_IMMUTABLE)
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(com.fusionlab.fusionmusic.R.drawable.ic_stat_fusion)
            .setContentTitle("Fusion Music 下载")
            .setContentText(text)
            .setContentIntent(pending)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
        if (total > 0 && !indeterminate) {
            builder.setProgress(1000, ((progress * 1000L) / total).toInt().coerceIn(0, 1000), false)
        } else {
            builder.setProgress(0, 0, true)
        }
        return builder.build()
    }

    private fun startForegroundCompat(notification: Notification) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            val channel = NotificationChannel(CHANNEL_ID, "下载", NotificationManager.IMPORTANCE_LOW)
            manager.createNotificationChannel(channel)
        }
    }

    private fun readHead(file: File, count: Int): ByteArray {
        return try {
            file.inputStream().use { stream ->
                val buffer = ByteArray(count)
                val read = stream.read(buffer)
                if (read <= 0) ByteArray(0) else buffer.copyOf(read)
            }
        } catch (_: Exception) {
            ByteArray(0)
        }
    }

    private data class Downloaded(val file: File, val suffix: String, val bytes: Long?)

    companion object {
        const val ACTION_START = "com.fusionlab.fusionmusic.DOWNLOAD_START"
        private const val CHANNEL_ID = "fusion_downloads"
        private const val NOTIFICATION_ID = 1002
    }
}
