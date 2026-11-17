package com.fusionlab.fusionmusic.playback

import android.content.Context
import android.net.Uri
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.core.util.AudioSniffer
import com.fusionlab.fusionmusic.data.net.Crypto
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

data class CachedMedia(val file: File, val suffix: String)

class MediaCache(context: Context, private val log: AppLog) {
    private val cacheDir = File(context.filesDir, "data/cache/media").apply { mkdirs() }
    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .build()

    fun download(
        url: String,
        headers: Map<String, String>,
        cookies: Map<String, String>,
        identity: String,
        expectedSeconds: Int = 0,
        suffix: String = ""
    ): CachedMedia? {
        if (url.isBlank()) return null
        val key = Crypto.sha256Bytes(identity.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it.toInt() and 0xFF) }
        val existing = findExisting(key)
        if (existing != null) return existing

        val requestBuilder = Request.Builder().url(url)
        for ((name, value) in headers) requestBuilder.header(name, value)
        if (cookies.isNotEmpty()) {
            val cookieHeader = cookies.entries.joinToString("; ") { it.key + "=" + it.value }
            requestBuilder.header("Cookie", cookieHeader)
        }
        val temp = File(cacheDir, key + ".part")
        val target = File(cacheDir, key + suffix.ifBlank { ".audio" })
        return try {
            client.newCall(requestBuilder.build()).execute().use { response ->
                if (!response.isSuccessful) return null
                val body = response.body ?: return null
                FileOutputStream(temp).use { output ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            val count = input.read(buffer)
                            if (count <= 0) break
                            output.write(buffer, 0, count)
                        }
                        output.fd.sync()
                    }
                }
            }
            if (!AudioSniffer.isAudioFile(temp)) {
                temp.delete()
                return null
            }
            val actualSuffix = if (suffix.isNotBlank()) suffix else {
                AudioSniffer.sniffSuffix(readHead(temp, 16)).ifBlank { ".audio" }
            }
            val finalFile = File(cacheDir, key + actualSuffix)
            if (!temp.renameTo(finalFile)) {
                temp.copyTo(finalFile, overwrite = true)
                temp.delete()
            }
            if (expectedSeconds > 0) {
                val actual = AudioSniffer.probeFileDuration(finalFile.absolutePath)
                if (!AudioSniffer.durationMatches(expectedSeconds, actual)) {
                    finalFile.delete()
                    return null
                }
            }
            CachedMedia(finalFile, actualSuffix)
        } catch (error: Exception) {
            temp.delete()
            log.w("MediaCache", "download failed: " + error.message)
            null
        }
    }

    fun stats(): Long {
        return cacheDir.listFiles()?.filter { it.isFile }?.sumOf { it.length() } ?: 0L
    }

    fun clear() {
        cacheDir.listFiles()?.forEach { it.delete() }
    }

    fun trim(maxBytes: Long) {
        if (maxBytes <= 0) return
        val files = cacheDir.listFiles()?.filter { it.isFile }?.sortedBy { it.lastModified() } ?: return
        var total = files.sumOf { it.length() }
        for (file in files) {
            if (total <= maxBytes) break
            total -= file.length()
            file.delete()
        }
    }

    private fun findExisting(key: String): CachedMedia? {
        val files = cacheDir.listFiles()?.filter { it.isFile && it.name.startsWith(key + ".") && !it.name.endsWith(".part") } ?: return null
        val file = files.maxByOrNull { it.lastModified() } ?: return null
        file.setLastModified(System.currentTimeMillis())
        val suffix = "." + file.name.substringAfter('.').ifBlank { "audio" }
        return CachedMedia(file, suffix)
    }

    fun uriFor(file: File): Uri = Uri.fromFile(file)

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
}
