package com.fusionlab.fusionmusic.playback

import android.content.Context
import android.net.Uri
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.Crypto
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

/**
 * 媒体通知的封面缓存。
 *
 * 系统通知栏不一定会替我们下载远程 artworkUri；先落到本机再交给 Media3，
 * 通知与锁屏就能稳定显示。封面按 URL 哈希命名，重复播放不会重复下载。
 */
class ArtworkCache(context: Context, private val log: AppLog) {
    private val dir = File(context.filesDir, "data/cache/cover").apply { mkdirs() }
    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()
    private val lock = Any()

    fun cached(url: String): Uri? {
        val file = fileFor(url)
        return if (file.exists() && file.length() > 0L) Uri.fromFile(file) else null
    }

    suspend fun ensure(url: String): Uri? = withContext(Dispatchers.IO) {
        synchronized(lock) {
        if (url.isBlank()) return@withContext null
        if (!url.startsWith("http://") && !url.startsWith("https://")) return@withContext null
        dir.mkdirs()
        val target = fileFor(url)
        if (target.exists() && target.length() > 0L) return@withContext Uri.fromFile(target)
        val temp = File(dir, target.name + ".part")
        try {
            client.newCall(
                Request.Builder().url(url)
                    .header("User-Agent", "Mozilla/5.0 (Linux; Android 14) FusionMusic/1.0")
                    .build()
            ).execute().use { response ->
                if (!response.isSuccessful) return@withContext null
                val body = response.body ?: return@withContext null
                FileOutputStream(temp).use { output ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(32 * 1024)
                        var written = 0L
                        while (true) {
                            val read = input.read(buffer)
                            if (read <= 0) break
                            written += read
                            if (written > MAX_BYTES) throw IllegalStateException("封面过大")
                            output.write(buffer, 0, read)
                        }
                        if (written <= 0L) throw IllegalStateException("封面为空")
                        output.fd.sync()
                    }
                }
            }
            if (target.exists()) target.delete()
            if (!temp.renameTo(target)) {
                temp.copyTo(target, overwrite = true)
                temp.delete()
            }
            Uri.fromFile(target)
        } catch (error: Exception) {
            temp.delete()
            log.d("ArtworkCache", "cover cache failed: " + error.message)
            null
        }
        }
    }

    private fun fileFor(url: String): File {
        val key = Crypto.sha256Bytes(url.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 0xFF) }
            .take(40)
        return File(dir, key + ".img")
    }

    companion object {
        private const val MAX_BYTES = 6L * 1024L * 1024L
    }
}
