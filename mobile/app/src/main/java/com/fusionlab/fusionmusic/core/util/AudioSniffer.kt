package com.fusionlab.fusionmusic.core.util

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import java.io.File

object AudioSniffer {
    private val MAGIC = listOf(
        byteArrayOf(0x49, 0x44, 0x33) to ".mp3",
        byteArrayOf(0x66, 0x4C, 0x61, 0x43) to ".flac",
        byteArrayOf(0x4F, 0x67, 0x67, 0x53) to ".ogg",
        byteArrayOf(0x4D, 0x41, 0x43, 0x20) to ".ape",
        byteArrayOf(0x77, 0x76, 0x70, 0x6B) to ".wv",
        byteArrayOf(0x30, 0x26, 0xB2.toByte(), 0x75) to ".wma"
    )

    fun sniffSuffix(head: ByteArray): String {
        if (head.isEmpty()) return ""
        for ((magic, suffix) in MAGIC) {
            if (startsWith(head, magic)) return suffix
        }
        if (head.size >= 12 && startsWith(head, "RIFF".toByteArray()) &&
            startsWith(head.copyOfRange(8, head.size), "WAVE".toByteArray())
        ) {
            return ".wav"
        }
        if (head.size >= 8 && startsWith(head.copyOfRange(4, head.size), "ftyp".toByteArray())) {
            return ".m4a"
        }
        if (head.size >= 2 && (head[0].toInt() and 0xFF) == 0xFF && (head[1].toInt() and 0xE0) == 0xE0) {
            val second = head[1].toInt() and 0xFF
            return if (second == 0xF1 || second == 0xF9) ".aac" else ".mp3"
        }
        return ""
    }

    fun isAudioFile(file: File): Boolean {
        if (!file.exists() || file.length() <= 0L) return false
        return try {
            val head = file.inputStream().use { stream ->
                val buffer = ByteArray(16)
                val count = stream.read(buffer)
                if (count <= 0) ByteArray(0) else buffer.copyOf(count)
            }
            sniffSuffix(head).isNotBlank()
        } catch (_: Exception) {
            false
        }
    }

    fun probeDuration(context: Context, uri: Uri): Int {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(context, uri)
            val raw = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
            val ms = raw?.toLongOrNull() ?: 0L
            if (ms > 0) (ms / 1000).toInt() else 0
        } catch (_: Exception) {
            0
        } finally {
            try {
                retriever.release()
            } catch (_: Exception) {
                // ignore
            }
        }
    }

    fun probeFileDuration(path: String): Int {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(path)
            val raw = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
            val ms = raw?.toLongOrNull() ?: 0L
            if (ms > 0) (ms / 1000).toInt() else 0
        } catch (_: Exception) {
            0
        } finally {
            try {
                retriever.release()
            } catch (_: Exception) {
                // ignore
            }
        }
    }

    fun durationMatches(expectedSeconds: Int, actualSeconds: Int): Boolean {
        if (expectedSeconds <= 0) return true
        if (actualSeconds <= 0) return true
        val tolerance = maxOf(10, (expectedSeconds * 0.2).toInt())
        return kotlin.math.abs(actualSeconds - expectedSeconds) <= tolerance
    }

    private fun startsWith(data: ByteArray, prefix: ByteArray): Boolean {
        if (data.size < prefix.size) return false
        for (index in prefix.indices) {
            if (data[index] != prefix[index]) return false
        }
        return true
    }
}
