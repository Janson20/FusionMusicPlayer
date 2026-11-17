package com.fusionlab.fusionmusic.data.update

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

data class Version(
    val major: Int,
    val minor: Int,
    val patch: Int,
    val pre: String = ""
) {
    override fun toString(): String {
        return "$major.$minor.$patch" + if (pre.isNotBlank()) "-$pre" else ""
    }
}

private val ASSET_DIGEST_RE = Regex("^sha256:([0-9a-fA-F]{64})$")

data class ReleaseAsset(
    val name: String,
    val url: String,
    val size: Long = 0L,
    val digest: String = ""
) {
    val sha256: String
        get() {
            val match = ASSET_DIGEST_RE.matchEntire(digest.trim()) ?: return ""
            return match.groupValues[1].lowercase()
        }
}

data class ReleaseInfo(
    val version: String,
    val tag: String,
    val name: String,
    val body: String,
    val htmlUrl: String,
    val publishedAt: String,
    val prerelease: Boolean,
    val assets: List<ReleaseAsset>
) {
    fun assetForAndroid(): ReleaseAsset? {
        val apks = assets.filter { it.name.endsWith(".apk", ignoreCase = true) }
            .filterNot { it.name.contains("debug", ignoreCase = true) }
        if (apks.isEmpty()) return null
        val exact = "FusionMusicPlayer-" + version + "-release.apk"
        apks.firstOrNull { it.name == exact }?.let { return it }
        apks.firstOrNull {
            it.name.contains(version, ignoreCase = true) && it.name.contains("release", ignoreCase = true)
        }?.let { return it }
        return apks.first()
    }

    fun checksumFor(asset: ReleaseAsset): ReleaseAsset? =
        assets.firstOrNull { it.name == asset.name + ".sha256" }
}

object Updater {
    const val DEFAULT_REPO = "Janson20/FusionMusicPlayer"
    const val GITHUB_API = "https://api.github.com"
    const val USER_AGENT = "FusionMusicPlayer-Android-Updater/1.0 (+https://github.com/Janson20/FusionMusicPlayer)"
    private val VERSION_RE = Regex("^\\s*v?(\\d+)\\.(\\d+)\\.(\\d+)(?:[-+]([0-9A-Za-z.\\-]+))?\\s*$")

    fun parseVersion(text: String): Version? {
        val match = VERSION_RE.matchEntire(text) ?: return null
        return Version(
            match.groupValues[1].toInt(),
            match.groupValues[2].toInt(),
            match.groupValues[3].toInt(),
            match.groupValues[4].lowercase()
        )
    }

    fun compareVersions(left: String, right: String): Int? {
        val a = parseVersion(left) ?: return null
        val b = parseVersion(right) ?: return null
        val core = when {
            a.major != b.major -> a.major.compareTo(b.major)
            a.minor != b.minor -> a.minor.compareTo(b.minor)
            else -> a.patch.compareTo(b.patch)
        }
        if (core != 0) return if (core > 0) 1 else -1
        if (a.pre == b.pre) return 0
        if (a.pre.isEmpty()) return 1
        if (b.pre.isEmpty()) return -1
        return if (a.pre > b.pre) 1 else -1
    }

    fun isNewer(candidate: String, current: String): Boolean = compareVersions(candidate, current) == 1

    fun urlAllowed(url: String): Boolean {
        return try {
            val uri = java.net.URI(url)
            if (!uri.scheme.equals("https", ignoreCase = true)) return false
            val host = uri.host?.lowercase() ?: return false
            ALLOWED_HOSTS.any { host == it || host.endsWith("." + it) }
        } catch (_: Exception) {
            false
        }
    }

    fun parseRelease(payload: JsonObject): ReleaseInfo? {
        val tag = payload["tag_name"]?.jsonPrimitive?.content?.trim().orEmpty()
        val version = parseVersion(tag) ?: return null
        val assets = mutableListOf<ReleaseAsset>()
        payload["assets"]?.jsonArray?.forEach { element ->
            val item = element as? JsonObject ?: return@forEach
            val name = item["name"]?.jsonPrimitive?.content?.trim().orEmpty()
            val url = item["browser_download_url"]?.jsonPrimitive?.content?.trim().orEmpty()
            if (name.isBlank() || url.isBlank() || !urlAllowed(url)) return@forEach
            val size = item["size"]?.jsonPrimitive?.content?.toLongOrNull() ?: 0L
            val digest = item["digest"]?.jsonPrimitive?.content.orEmpty()
            assets.add(ReleaseAsset(name, url, size, digest))
        }
        return ReleaseInfo(
            version = version.toString(),
            tag = tag,
            name = payload["name"]?.jsonPrimitive?.content.orEmpty().ifBlank { tag },
            body = payload["body"]?.jsonPrimitive?.content.orEmpty(),
            htmlUrl = payload["html_url"]?.jsonPrimitive?.content.orEmpty(),
            publishedAt = payload["published_at"]?.jsonPrimitive?.content.orEmpty(),
            prerelease = payload["prerelease"]?.jsonPrimitive?.content == "true",
            assets = assets
        )
    }

    fun parseLatest(text: String): ReleaseInfo? {
        return try {
            parseRelease(Json.parseToJsonElement(text).jsonObject)
        } catch (_: Exception) {
            null
        }
    }

    fun parseLatestList(text: String): ReleaseInfo? {
        return try {
            val array = Json.parseToJsonElement(text).jsonArray
            for (element in array) {
                val item = element as? JsonObject ?: continue
                if (item["draft"]?.jsonPrimitive?.content == "true") continue
                parseRelease(item)?.let { return it }
            }
            null
        } catch (_: Exception) {
            null
        }
    }

    fun releaseNotesExcerpt(body: String, limit: Int = 900): String {
        val lines = body.lines().filterNot {
            val trimmed = it.trim()
            trimmed.startsWith("|") || trimmed.startsWith(">")
        }
        var text = lines.joinToString("\n").trim()
        if (text.length > limit) text = text.take(limit).trimEnd() + "…"
        return text
    }

    fun buildClient(timeoutSeconds: Int, proxy: String = ""): OkHttpClient {
        val builder = OkHttpClient.Builder()
            .connectTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
            .readTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
            .writeTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
            .followRedirects(true)
        val parts = proxy.trim().split(":", limit = 2)
        if (parts.size == 2) {
            val port = parts[1].toIntOrNull()
            if (port != null) {
                try {
                    builder.proxy(java.net.Proxy(java.net.Proxy.Type.HTTP, java.net.InetSocketAddress(parts[0], port)))
                } catch (_: Exception) {
                    // 无效代理按直连处理。
                }
            }
        }
        return builder.build()
    }

    fun apiRequest(url: String): Request {
        return Request.Builder()
            .url(url)
            .header("User-Agent", USER_AGENT)
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
            .get()
            .build()
    }

    fun sha256File(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { stream ->
            val buffer = ByteArray(1024 * 1024)
            while (true) {
                val read = stream.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xFF) }
    }

    fun download(
        client: OkHttpClient,
        asset: ReleaseAsset,
        expectedSha256: String,
        targetDir: File,
        shouldCancel: () -> Boolean = { false },
        onProgress: (Long, Long) -> Unit
    ): File {
        if (!urlAllowed(asset.url)) throw IllegalStateException("下载地址不在允许的域名内，已拒绝")
        if (!SHA256_RE.matches(expectedSha256)) throw IllegalStateException("缺少有效的 SHA-256 校验值，已放弃自动更新")
        val safeName = asset.name.substringAfterLast('/').substringAfterLast('\\').trim()
        if (safeName.isBlank() || safeName == "." || safeName == "..") {
            throw IllegalStateException("更新文件名不合法，已拒绝")
        }
        targetDir.mkdirs()
        val target = File(targetDir, safeName)
        val part = File(targetDir, safeName + ".part")
        val digest = MessageDigest.getInstance("SHA-256")
        var received = 0L
        var total = asset.size
        try {
            client.newCall(Request.Builder().url(asset.url).header("User-Agent", USER_AGENT).build()).execute().use { response ->
                if (!response.isSuccessful) throw IllegalStateException("下载失败：HTTP " + response.code)
                if (!urlAllowed(response.request.url.toString())) {
                    throw IllegalStateException("下载被重定向到不允许的域名，已拒绝")
                }
                val body = response.body ?: throw IllegalStateException("下载内容为空")
                total = if (body.contentLength() > 0) body.contentLength() else total
                FileOutputStream(part).use { output ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(256 * 1024)
                        var lastReport = 0L
                        while (true) {
                            if (shouldCancel()) throw IllegalStateException("已取消下载")
                            val read = input.read(buffer)
                            if (read <= 0) break
                            output.write(buffer, 0, read)
                            digest.update(buffer, 0, read)
                            received += read
                            val now = System.currentTimeMillis()
                            if (now - lastReport >= 250) {
                                onProgress(received, total)
                                lastReport = now
                            }
                        }
                        output.fd.sync()
                    }
                }
            }
            if (received <= 0L) throw IllegalStateException("下载内容为空")
            val actual = digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xFF) }
            if (!actual.equals(expectedSha256, ignoreCase = true)) {
                throw IllegalStateException("下载内容校验失败（SHA-256 不匹配），已删除")
            }
            if (target.exists()) target.delete()
            if (!part.renameTo(target)) {
                part.copyTo(target, overwrite = true)
                part.delete()
            }
            onProgress(received, if (total > 0) total else received)
            return target
        } catch (error: Exception) {
            part.delete()
            throw error
        }
    }

    fun parseChecksum(text: String): String? {
        val first = text.trim().lineSequence().firstOrNull()?.trim() ?: return null
        val token = first.substringBefore(' ').trim()
        return if (SHA256_RE.matches(token)) token.lowercase() else null
    }

    private val SHA256_RE = Regex("[0-9a-fA-F]{64}")
    private val ALLOWED_HOSTS = listOf(
        "github.com",
        "api.github.com",
        "objects.githubusercontent.com",
        "release-assets.githubusercontent.com",
        "codeload.github.com"
    )
}
