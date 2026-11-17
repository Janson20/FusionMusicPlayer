package com.fusionlab.fusionmusic.data.net

import com.fusionlab.fusionmusic.core.util.AppLog
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.FormBody
import okhttp3.Headers
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Proxy
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlin.random.Random

class HttpEngine(
    timeoutSeconds: Int = 15,
    proxy: String = "",
    private val log: AppLog? = null
) {
    val cookieJar = MemoryCookieJar()
    private val client: OkHttpClient
    private val defaultUserAgent = USER_AGENTS[Random.nextInt(USER_AGENTS.size)]

    init {
        val builder = OkHttpClient.Builder()
            .connectTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
            .readTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
            .writeTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .cookieJar(cookieJar)

        val proxyValue = parseProxy(proxy)
        if (proxyValue != null) builder.proxy(proxyValue)
        client = builder.build()
    }

    fun get(
        url: String,
        query: Map<String, String> = emptyMap(),
        headers: Map<String, String> = emptyMap()
    ): Response {
        val target = buildUrl(url, query) ?: throw IOException("bad url: " + url)
        val request = Request.Builder()
            .url(target)
            .headers(defaultHeaders().toOkHttpHeaders())
            .headers(headers.toOkHttpHeaders())
            .get()
            .build()
        return executeWithRetry(request)
    }

    fun postForm(
        url: String,
        form: Map<String, String> = emptyMap(),
        headers: Map<String, String> = emptyMap()
    ): Response {
        val bodyBuilder = FormBody.Builder()
        form.forEach { (key, value) -> bodyBuilder.add(key, value) }
        val request = Request.Builder()
            .url(url)
            .headers(defaultHeaders().toOkHttpHeaders())
            .headers(headers.toOkHttpHeaders())
            .post(bodyBuilder.build())
            .build()
        return executeWithRetry(request)
    }

    fun postBytes(
        url: String,
        bytes: ByteArray,
        contentType: String = "application/x-www-form-urlencoded; charset=UTF-8",
        headers: Map<String, String> = emptyMap()
    ): Response {
        val request = Request.Builder()
            .url(url)
            .headers(defaultHeaders().toOkHttpHeaders())
            .headers(headers.toOkHttpHeaders())
            .post(bytes.toRequestBody(contentType.toMediaType()))
            .build()
        return executeWithRetry(request)
    }

    fun getText(
        url: String,
        query: Map<String, String> = emptyMap(),
        headers: Map<String, String> = emptyMap()
    ): String? {
        return try {
            get(url, query, headers).use { response ->
                if (!response.isSuccessful) return null
                response.body?.string()
            }
        } catch (error: Exception) {
            log?.w(TAG, "GET failed: " + url + " / " + error.message)
            null
        }
    }

    fun getBytes(
        url: String,
        headers: Map<String, String> = emptyMap()
    ): ByteArray? {
        return try {
            get(url, emptyMap(), headers).use { response ->
                if (!response.isSuccessful) return null
                response.body?.bytes()
            }
        } catch (error: Exception) {
            log?.w(TAG, "GET bytes failed: " + url + " / " + error.message)
            null
        }
    }

    fun postFormText(
        url: String,
        form: Map<String, String> = emptyMap(),
        headers: Map<String, String> = emptyMap()
    ): String? {
        return try {
            postForm(url, form, headers).use { response ->
                if (!response.isSuccessful) return null
                response.body?.string()
            }
        } catch (error: Exception) {
            log?.w(TAG, "POST failed: " + url + " / " + error.message)
            null
        }
    }

    fun postBytesResponse(
        url: String,
        bytes: ByteArray,
        contentType: String = "application/x-www-form-urlencoded; charset=UTF-8",
        headers: Map<String, String> = emptyMap()
    ): Response {
        return postBytes(url, bytes, contentType, headers)
    }

    fun cookieHeader(): String = cookieJar.cookieHeader()

    fun cookieValue(name: String): String? = cookieJar.cookieValue(name)

    fun cookieExpiry(name: String): Long? = cookieJar.cookieExpiry(name)

    fun applyCookieString(raw: String, domain: String) {
        cookieJar.applyCookieString(raw, domain)
    }

    fun setCookie(name: String, value: String, domain: String, path: String = "/", expiresAt: Long = Long.MAX_VALUE) {
        cookieJar.put(name, value, domain, path, expiresAt)
    }

    fun clearCookies(keepNames: Set<String> = emptySet()) {
        cookieJar.clear(keepNames)
    }

    private fun Map<String, String>.toOkHttpHeaders(): Headers =
        Headers.Builder().apply { forEach { (name, value) -> add(name, value) } }.build()

    private fun defaultHeaders(): Map<String, String> = mapOf(
        "User-Agent" to defaultUserAgent,
        "Accept" to "application/json, text/plain, */*",
        "Accept-Language" to "zh-CN,zh;q=0.9,en;q=0.8"
    )

    private fun buildUrl(url: String, query: Map<String, String>): HttpUrl? {
        val base = url.toHttpUrlOrNull() ?: return null
        if (query.isEmpty()) return base
        val builder = base.newBuilder()
        query.forEach { (key, value) -> builder.addQueryParameter(key, value) }
        return builder.build()
    }

    private fun executeWithRetry(request: Request): Response {
        var lastError: IOException? = null
        for (attempt in 0 until MAX_ATTEMPTS) {
            try {
                val response = client.newCall(request).execute()
                val code = response.code
                if (code == 408 || code == 429 || code in 500..599) {
                    response.close()
                    if (attempt < MAX_ATTEMPTS - 1) {
                        sleepBackoff(attempt)
                        continue
                    }
                }
                return response
            } catch (error: IOException) {
                lastError = error
                if (attempt < MAX_ATTEMPTS - 1) sleepBackoff(attempt)
            }
        }
        throw lastError ?: IOException("request failed")
    }

    private fun sleepBackoff(attempt: Int) {
        try {
            Thread.sleep((RETRY_BASE_MS shl attempt).toLong())
        } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
    }

    private fun parseProxy(value: String): Proxy? {
        val text = value.trim()
        if (text.isEmpty()) return null
        val parts = text.split(":", limit = 2)
        if (parts.size != 2) return null
        val port = parts[1].toIntOrNull() ?: return null
        return try {
            Proxy(Proxy.Type.HTTP, InetSocketAddress(parts[0], port))
        } catch (_: Exception) {
            null
        }
    }

    class MemoryCookieJar : CookieJar {
        private val cookies = LinkedHashMap<String, Cookie>()

        @Synchronized
        override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
            for (cookie in cookies) {
                val key = cookie.domain + "|" + cookie.path + "|" + cookie.name
                this.cookies[key] = cookie
            }
        }

        @Synchronized
        override fun loadForRequest(url: HttpUrl): List<Cookie> {
            val now = System.currentTimeMillis()
            return cookies.values.filter { cookie ->
                cookie.expiresAt > now && cookie.matches(url)
            }
        }

        @Synchronized
        fun cookieHeader(): String = cookies.values.joinToString("; ") { it.name + "=" + it.value }

        @Synchronized
        fun cookieValue(name: String): String? = cookies.values.lastOrNull { it.name == name }?.value

        @Synchronized
        fun cookieExpiry(name: String): Long? = cookies.values.lastOrNull { it.name == name }?.expiresAt

        @Synchronized
        fun put(name: String, value: String, domain: String, path: String, expiresAt: Long) {
            if (name.isBlank()) return
            // OkHttp rejects a leading dot, while both Netease and Bilibili hand us
            // domains in the legacy Set-Cookie form, e.g. ".music.163.com".
            val normalizedDomain = normalizeCookieDomain(domain) ?: return
            val safePath = if (path.startsWith("/")) path else "/"
            try {
                val builder = Cookie.Builder()
                    .name(name)
                    .value(value)
                    .domain(normalizedDomain)
                    .path(safePath)
                if (expiresAt != Long.MAX_VALUE) builder.expiresAt(expiresAt)
                val cookie = builder.build()
                cookies[cookie.domain + "|" + cookie.path + "|" + cookie.name] = cookie
            } catch (_: IllegalArgumentException) {
                // A malformed cookie must not take down a network request or startup.
            }
        }

        @Synchronized
        fun applyCookieString(raw: String, domain: String) {
            for (part in raw.split(";")) {
                val pair = part.trim()
                if (pair.isEmpty() || !pair.contains("=")) continue
                val index = pair.indexOf('=')
                val name = pair.substring(0, index).trim()
                val value = pair.substring(index + 1).trim()
                if (name.isEmpty()) continue
                put(name, value, domain, "/", Long.MAX_VALUE)
            }
        }

        @Synchronized
        fun clear(keepNames: Set<String>) {
            if (keepNames.isEmpty()) {
                cookies.clear()
            } else {
                cookies.entries.removeAll { !keepNames.contains(it.value.name) }
            }
        }
    }

    companion object {
        private const val TAG = "HttpEngine"

        private fun normalizeCookieDomain(domain: String): String? {
            val value = domain.trim().trimStart('.').trimEnd('.').lowercase(Locale.US)
            if (value.isEmpty()) return null
            if (value.any { it.isWhitespace() } || '/' in value || ':' in value) return null
            return value
        }
        private const val MAX_ATTEMPTS = 3
        private const val RETRY_BASE_MS = 800
        private val USER_AGENTS = listOf(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"
        )
    }
}
