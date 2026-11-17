package com.fusionlab.fusionmusic.data.download

import com.fusionlab.fusionmusic.core.model.Track
import com.fusionlab.fusionmusic.core.util.AppLog
import org.jaudiotagger.audio.AudioFileIO
import org.jaudiotagger.tag.FieldKey
import org.jaudiotagger.tag.TagOptionSingleton
import org.jaudiotagger.tag.images.ArtworkFactory
import java.io.File

object TagWriter {
    private var initialized = false

    fun write(
        file: File,
        track: Track,
        coverBytes: ByteArray?,
        log: AppLog
    ): String? {
        if (!initialized) {
            try {
                TagOptionSingleton.getInstance().setAndroid(true)
            } catch (_: Throwable) {
                // If the Android switch is unavailable, keep the default path.
            }
            initialized = true
        }
        return try {
            val audioFile = AudioFileIO.read(file)
            val tag = audioFile.tag ?: return "音频没有可写的标签容器"
            setSafe(tag, FieldKey.TITLE, track.name)
            setSafe(tag, FieldKey.ARTIST, track.singer)
            setSafe(tag, FieldKey.ALBUM, track.album)
            val year = publishYear(track.publishTime)
            if (year > 0) setSafe(tag, FieldKey.YEAR, year.toString())
            if (coverBytes != null && coverBytes.isNotEmpty()) {
                try {
                    val artwork = ArtworkFactory.getNew()
                    artwork.binaryData = coverBytes
                    artwork.mimeType = imageMime(coverBytes)
                    artwork.pictureType = 3
                    tag.setField(artwork)
                } catch (error: Throwable) {
                    log.w("TagWriter", "cover embed failed: " + (error.message ?: error.javaClass.simpleName))
                }
            }
            audioFile.commit()
            null
        } catch (error: Throwable) {
            log.w("TagWriter", "tag write failed: " + (error.message ?: error.javaClass.simpleName))
            error.message ?: "标签写入失败"
        }
    }

    private fun setSafe(tag: org.jaudiotagger.tag.Tag, key: FieldKey, value: String) {
        if (value.isBlank()) return
        try {
            tag.setField(key, value)
        } catch (_: Throwable) {
            // Some containers do not support every field; keep the audio usable.
        }
    }

    private fun publishYear(timestamp: Long): Int {
        if (timestamp <= 0) return 0
        val millis = if (timestamp < 10_000_000_000L) timestamp * 1000L else timestamp
        return try {
            java.time.Instant.ofEpochMilli(millis).atZone(java.time.ZoneId.systemDefault()).year
        } catch (_: Exception) {
            0
        }
    }

    private fun imageMime(bytes: ByteArray): String {
        if (bytes.size >= 3 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xD8.toByte()) return "image/jpeg"
        if (bytes.size >= 4 && bytes[0] == 0x89.toByte() && bytes[1] == 0x50.toByte()) return "image/png"
        if (bytes.size >= 12 && bytes[8] == 0x57.toByte() && bytes[9] == 0x45.toByte() && bytes[10] == 0x42.toByte()) return "image/webp"
        return "image/jpeg"
    }
}
