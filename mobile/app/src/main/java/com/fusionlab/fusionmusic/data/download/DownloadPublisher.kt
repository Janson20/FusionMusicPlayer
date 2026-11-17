package com.fusionlab.fusionmusic.data.download

import android.content.ContentValues
import android.content.Context
import android.content.pm.PackageManager
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.ContextCompat
import androidx.documentfile.provider.DocumentFile
import com.fusionlab.fusionmusic.core.util.Naming
import java.io.File

data class PublishResult(
    val uri: Uri?,
    val path: String,
    val skipped: Boolean = false,
    val message: String = ""
)

object DownloadPublisher {
    fun publish(
        context: Context,
        source: File,
        displayStem: String,
        suffix: String,
        duplicate: String,
        downloadDir: String
    ): PublishResult {
        return try {
            if (downloadDir.startsWith("content://")) {
                publishSaf(context, source, displayStem, suffix, duplicate, downloadDir)
            } else {
                publishMediaStore(context, source, displayStem, suffix, duplicate)
            }
        } catch (error: SecurityException) {
            PublishResult(
                null,
                "",
                message = "存储权限不足或下载目录授权已失效，请在设置中重新选择目录"
            )
        }
    }

    fun writeLyric(
        context: Context,
        audioStem: String,
        lyric: String,
        downloadDir: String
    ): String? {
        if (lyric.isBlank()) return null
        return if (downloadDir.startsWith("content://")) {
            writeLyricSaf(context, audioStem, lyric, downloadDir)
        } else {
            writeLyricMediaStore(context, audioStem, lyric)
        }
    }

    private fun publishMediaStore(
        context: Context,
        source: File,
        displayStem: String,
        suffix: String,
        duplicate: String
    ): PublishResult {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            val dir = legacyMusicDir(context)
            var target = File(dir, displayStem + suffix)
            if (target.exists()) {
                when (duplicate) {
                    "skip" -> return PublishResult(null, target.absolutePath, skipped = true)
                    "overwrite" -> target.delete()
                    else -> target = uniqueFile(dir, displayStem, suffix)
                }
            }
            try {
                source.copyTo(target, overwrite = true)
                scanLegacyAudio(context, target, suffix)
                return PublishResult(Uri.fromFile(target), target.absolutePath)
            } catch (_: Exception) {
                target.delete()
                return publishAppPrivate(context, source, displayStem, suffix, duplicate)
                    .copy(message = "公共音乐目录不可写，已保存到应用专属目录")
            }
        }
        val resolver = context.contentResolver
        val relative = Environment.DIRECTORY_MUSIC + "/FusionMusicPlayer"
        val collection = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        val baseName = displayStem + suffix
        var targetName = baseName
        val existing = queryExisting(resolver, collection, relative, targetName)
        if (existing != null) {
            when (duplicate) {
                "skip" -> return PublishResult(null, existing.toString(), skipped = true)
                "overwrite" -> resolver.delete(existing, null, null)
                else -> targetName = uniqueMediaName(resolver, collection, relative, displayStem, suffix)
            }
        }
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, targetName)
            put(MediaStore.MediaColumns.MIME_TYPE, Naming.audioMime(suffix))
            put(MediaStore.MediaColumns.RELATIVE_PATH, relative)
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = try {
            resolver.insert(collection, values)
        } catch (error: Exception) {
            null
        }
        if (uri == null) {
            return publishPrivateFallback(
                context = context,
                source = source,
                displayStem = displayStem,
                suffix = suffix,
                duplicate = duplicate,
                reason = "无法写入系统媒体库"
            )
        }
        try {
            resolver.openOutputStream(uri)?.use { output ->
                source.inputStream().use { input -> input.copyTo(output) }
            } ?: throw IllegalStateException("无法打开输出流")
            val done = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
            resolver.update(uri, done, null, null)
            return PublishResult(uri, uri.toString())
        } catch (error: Exception) {
            try {
                resolver.delete(uri, null, null)
            } catch (_: Exception) {
                // ignore cleanup failure
            }
            return publishPrivateFallback(
                context = context,
                source = source,
                displayStem = displayStem,
                suffix = suffix,
                duplicate = duplicate,
                reason = error.message ?: "写入系统媒体库失败"
            )
        }
    }

    private fun publishPrivateFallback(
        context: Context,
        source: File,
        displayStem: String,
        suffix: String,
        duplicate: String,
        reason: String
    ): PublishResult {
        val fallback = try {
            publishAppPrivate(context, source, displayStem, suffix, duplicate)
        } catch (_: Exception) {
            null
        }
        if (fallback?.skipped == true) return fallback
        return if (fallback?.uri != null) {
            fallback.copy(message = reason + "，已保存到应用专属目录")
        } else {
            PublishResult(null, "", message = reason + "，请检查存储空间或在设置中选择其他下载目录")
        }
    }

    private fun publishAppPrivate(
        context: Context,
        source: File,
        displayStem: String,
        suffix: String,
        duplicate: String
    ): PublishResult {
        val base = context.getExternalFilesDir(Environment.DIRECTORY_MUSIC)
            ?: File(context.filesDir, "music")
        val dir = File(base, "FusionMusicPlayer").apply { mkdirs() }
        var target = File(dir, displayStem + suffix)
        if (target.exists()) {
            when (duplicate) {
                "skip" -> return PublishResult(null, target.absolutePath, skipped = true)
                "overwrite" -> target.delete()
                else -> target = uniqueFile(dir, displayStem, suffix)
            }
        }
        source.copyTo(target, overwrite = true)
        return PublishResult(Uri.fromFile(target), target.absolutePath)
    }

    private fun publishSaf(
        context: Context,
        source: File,
        displayStem: String,
        suffix: String,
        duplicate: String,
        downloadDir: String
    ): PublishResult {
        val tree = DocumentFile.fromTreeUri(context, Uri.parse(downloadDir))
            ?: return PublishResult(null, "", message = "下载目录不可用")
        val baseName = displayStem + suffix
        var target = tree.findFile(baseName)
        if (target != null) {
            when (duplicate) {
                "skip" -> return PublishResult(null, target.uri.toString(), skipped = true)
                "overwrite" -> target.delete()
                else -> {
                    var index = 1
                    while (tree.findFile(displayStem + " (" + index + ")" + suffix) != null) index += 1
                    target = tree.createFile(Naming.audioMime(suffix), displayStem + " (" + index + ")" + suffix)
                }
            }
        } else {
            target = tree.createFile(Naming.audioMime(suffix), baseName)
        }
        if (target == null) {
            return PublishResult(null, "", message = "无法创建下载文件，请在设置中重新选择下载目录")
        }
        return try {
            context.contentResolver.openOutputStream(target.uri)?.use { output ->
                source.inputStream().use { input -> input.copyTo(output) }
            } ?: throw IllegalStateException("无法打开输出流")
            PublishResult(target.uri, target.uri.toString())
        } catch (error: Exception) {
            try {
                target.delete()
            } catch (_: Exception) {
                // ignore
            }
            PublishResult(null, "", message = error.message ?: "写入下载目录失败")
        }
    }

    private fun writeLyricMediaStore(context: Context, audioStem: String, lyric: String): String? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            return try {
                val dir = legacyMusicDir(context)
                val file = File(dir, audioStem + ".lrc")
                file.writeText(lyric, Charsets.UTF_8)
                Uri.fromFile(file).toString()
            } catch (_: Exception) {
                null
            }
        }
        val resolver = context.contentResolver
        val name = audioStem + ".lrc"
        // MediaStore.Downloads only accepts the Download top-level directory.
        // Try the all-files collection first so the lyric can sit next to the
        // audio in Music, then fall back to the Download collection.
        val attempts = listOf(
            MediaStore.Files.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY) to
                (Environment.DIRECTORY_MUSIC + "/FusionMusicPlayer"),
            MediaStore.Downloads.EXTERNAL_CONTENT_URI to
                (Environment.DIRECTORY_DOWNLOADS + "/FusionMusicPlayer")
        )
        for ((collection, relative) in attempts) {
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, "text/plain")
                put(MediaStore.MediaColumns.RELATIVE_PATH, relative)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val uri = try {
                resolver.insert(collection, values)
            } catch (_: Exception) {
                null
            } ?: continue
            try {
                resolver.openOutputStream(uri)?.use { it.write(lyric.toByteArray(Charsets.UTF_8)) }
                    ?: throw IllegalStateException("无法打开歌词输出流")
                val done = ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) }
                resolver.update(uri, done, null, null)
                return uri.toString()
            } catch (_: Exception) {
                try {
                    resolver.delete(uri, null, null)
                } catch (_: Exception) {
                    // Try the next collection.
                }
            }
        }
        return null
    }

    private fun writeLyricSaf(context: Context, audioStem: String, lyric: String, downloadDir: String): String? {
        val tree = DocumentFile.fromTreeUri(context, Uri.parse(downloadDir)) ?: return null
        val existing = tree.findFile(audioStem + ".lrc")
        existing?.delete()
        val target = tree.createFile("text/plain", audioStem + ".lrc") ?: return null
        return try {
            context.contentResolver.openOutputStream(target.uri)?.use { it.write(lyric.toByteArray(Charsets.UTF_8)) }
            target.uri.toString()
        } catch (_: Exception) {
            null
        }
    }

    private fun legacyMusicDir(context: Context): File {
        val writablePublic = Build.VERSION.SDK_INT <= Build.VERSION_CODES.P &&
            ContextCompat.checkSelfPermission(
                context,
                android.Manifest.permission.WRITE_EXTERNAL_STORAGE
            ) == PackageManager.PERMISSION_GRANTED
        if (writablePublic) {
            val publicDir = File(
                Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC),
                "FusionMusicPlayer"
            )
            if (publicDir.mkdirs() || publicDir.isDirectory) return publicDir
        }
        val base = context.getExternalFilesDir(Environment.DIRECTORY_MUSIC)
            ?: File(context.filesDir, "music")
        return File(base, "FusionMusicPlayer").apply { mkdirs() }
    }

    private fun scanLegacyAudio(context: Context, file: File, suffix: String) {
        if (Build.VERSION.SDK_INT > Build.VERSION_CODES.P) return
        try {
            MediaScannerConnection.scanFile(
                context,
                arrayOf(file.absolutePath),
                arrayOf(Naming.audioMime(suffix)),
                null
            )
        } catch (_: Exception) {
            // The file is already written; a missing scanner does not invalidate it.
        }
    }

    private fun queryExisting(
        resolver: android.content.ContentResolver,
        collection: Uri,
        relative: String,
        name: String
    ): Uri? {
        val projection = arrayOf(MediaStore.MediaColumns._ID)
        val selection = MediaStore.MediaColumns.DISPLAY_NAME + "=? AND " + MediaStore.MediaColumns.RELATIVE_PATH + "=?"
        return try {
            resolver.query(collection, projection, selection, arrayOf(name, relative), null)?.use { cursor ->
                if (cursor.moveToFirst()) {
                    val id = cursor.getLong(0)
                    Uri.withAppendedPath(collection, id.toString())
                } else {
                    null
                }
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun uniqueMediaName(
        resolver: android.content.ContentResolver,
        collection: Uri,
        relative: String,
        stem: String,
        suffix: String
    ): String {
        var index = 1
        while (index < 1000) {
            val candidate = stem + " (" + index + ")" + suffix
            if (queryExisting(resolver, collection, relative, candidate) == null) return candidate
            index += 1
        }
        return stem + " (" + System.currentTimeMillis() + ")" + suffix
    }

    private fun uniqueFile(dir: File, stem: String, suffix: String): File {
        var index = 1
        while (index < 1000) {
            val candidate = File(dir, stem + " (" + index + ")" + suffix)
            if (!candidate.exists()) return candidate
            index += 1
        }
        return File(dir, stem + " (" + System.currentTimeMillis() + ")" + suffix)
    }
}
