package com.fusionlab.fusionmusic.data.account

import android.net.Uri
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.net.bool
import com.fusionlab.fusionmusic.data.net.int
import com.fusionlab.fusionmusic.data.net.long
import com.fusionlab.fusionmusic.data.net.obj
import com.fusionlab.fusionmusic.data.net.string
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.net.Proxy
import java.util.Base64
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

data class DesktopLoginCandidate(
    val cookies: String,
    val userId: Long,
    val nickname: String,
    val expiresAt: Long,
    val credential: JsonObject
)

class DesktopTransferException(message: String, cause: Throwable? = null) : Exception(message, cause)

/**
 * 接收桌面端一次性二维码里的加密登录凭据。
 *
 * 二维码携带 host/port/token/临时密钥；密文走局域网 HTTP，token 放在 Authorization
 * 头里，不拼进 URL。密钥只存在于二维码和本机内存，不发给桌面服务端。
 */
object DesktopLoginTransfer {
    private const val SCHEME = "fusionmusic"
    private const val HOST = "login-transfer"
    private const val VERSION = 1
    private const val AAD_PREFIX = "FusionMusicPlayer/login-transfer/v1"
    private const val MAX_RESPONSE_BYTES = 128 * 1024
    private const val MAX_URI_LENGTH = 4096

    private val json = Json { ignoreUnknownKeys = true; isLenient = true }
    private val emptyBody = ByteArray(0).toRequestBody("application/octet-stream".toMediaType())

    private val client: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(8, TimeUnit.SECONDS)
            .readTimeout(12, TimeUnit.SECONDS)
            .writeTimeout(8, TimeUnit.SECONDS)
            .callTimeout(18, TimeUnit.SECONDS)
            // 局域网直连，不走系统代理；代理会让 192.168.x.x 也绕出去
            .proxy(Proxy.NO_PROXY)
            .retryOnConnectionFailure(false)
            .build()
    }

    private data class TransferParams(
        val host: String,
        val port: Int,
        val token: String,
        val key: ByteArray,
        val expiresAt: Long
    )

    private data class TransferResponse(
        val nonce: ByteArray,
        val data: ByteArray,
        val expiresAt: Long
    )

    fun redeem(uriText: String, log: AppLog? = null): DesktopLoginCandidate {
        val params = parse(uriText)
        try {
            val response = fetch(params, log)
            val plaintext = decrypt(params, response)
            try {
                return parseCredential(plaintext)
            } finally {
                plaintext.fill(0)
            }
        } finally {
            params.key.fill(0)
        }
    }

    private fun parse(uriText: String): TransferParams {
        val text = uriText.trim()
        if (text.length > MAX_URI_LENGTH) throw DesktopTransferException("二维码内容过长")
        val uri = try {
            Uri.parse(text)
        } catch (_: Exception) {
            throw DesktopTransferException("二维码格式不正确")
        }
        if (uri.scheme != SCHEME || uri.host != HOST) {
            throw DesktopTransferException("这不是 Fusion Music 的手机登录二维码")
        }
        if (!uri.path.isNullOrBlank() && uri.path != "/") {
            throw DesktopTransferException("二维码地址不正确")
        }
        val version = uri.getQueryParameter("v")?.toIntOrNull()
        if (version != VERSION) throw DesktopTransferException("二维码版本不受支持，请更新电脑端")
        val host = uri.getQueryParameter("h").orEmpty()
        if (!isPrivateIpv4(host)) {
            throw DesktopTransferException("二维码里的电脑地址不是局域网地址")
        }
        val port = uri.getQueryParameter("p")?.toIntOrNull()
        if (port == null || port !in 1..65535) throw DesktopTransferException("二维码端口不正确")
        val tokenRaw = uri.getQueryParameter("t").orEmpty()
        val keyRaw = uri.getQueryParameter("k").orEmpty()
        val token = decodeBase64Url(tokenRaw, 32, "一次性令牌")
        val key = decodeBase64Url(keyRaw, 32, "传输密钥")
        val tokenText = encodeBase64Url(token)
        if (tokenText != tokenRaw) {
            throw DesktopTransferException("二维码令牌格式不正确")
        }
        val expiresAt = uri.getQueryParameter("e")?.toLongOrNull()
            ?: throw DesktopTransferException("二维码缺少有效期")
        if (expiresAt <= 0) throw DesktopTransferException("二维码有效期不正确")
        if (expiresAt < System.currentTimeMillis() / 1000L - 300L) {
            throw DesktopTransferException("二维码已过期，请在电脑上重新生成")
        }
        return TransferParams(host, port!!, tokenText, key, expiresAt)
    }

    private fun fetch(params: TransferParams, log: AppLog?): TransferResponse {
        val url = "http://" + params.host + ":" + params.port + "/v1/credential"
        val request = Request.Builder()
            .url(url)
            .post(emptyBody)
            .header("Authorization", "Bearer " + params.token)
            .header("Accept", "application/json")
            .header("Cache-Control", "no-store")
            .build()
        val response = try {
            client.newCall(request).execute()
        } catch (_: Exception) {
            log?.w("DesktopTransfer", "local request failed")
            throw DesktopTransferException("连不上电脑，请确认手机与电脑在同一 Wi-Fi，且电脑端二维码仍在显示")
        }
        response.use {
            if (!it.isSuccessful) {
                log?.w("DesktopTransfer", "local request HTTP " + it.code)
                throw when (it.code) {
                    401, 403 -> DesktopTransferException("二维码令牌无效，请重新生成")
                    409 -> DesktopTransferException("二维码已经被使用，请在电脑上重新生成")
                    410 -> DesktopTransferException("二维码已过期，请在电脑上重新生成")
                    else -> DesktopTransferException("电脑端没有接受登录请求，请重新生成二维码")
                }
            }
            val length = it.body?.contentLength() ?: -1L
            if (length > MAX_RESPONSE_BYTES) throw DesktopTransferException("电脑端返回的数据过大")
            val bytes = readLimited(it.body?.byteStream() ?: throw DesktopTransferException("电脑端返回为空"))
            val root = try {
                json.parseToJsonElement(String(bytes, Charsets.UTF_8)).jsonObject
            } catch (_: Exception) {
                throw DesktopTransferException("电脑端返回的数据格式不正确")
            } finally {
                bytes.fill(0)
            }
            if (!root.bool("ok")) throw DesktopTransferException("电脑端没有发送登录凭据")
            if (root.int("v") != VERSION) throw DesktopTransferException("电脑端协议版本不匹配")
            if (root.string("alg") != "AES-256-GCM") throw DesktopTransferException("不支持的加密方式")
            val nonce = decodeBase64Url(root.string("nonce"), 12, "随机数")
            // 密文是整份凭据 JSON，base64 后通常一两千字符；不能套用
            // token/key 的 512 字符上限，否则会把正常密文判成“格式不正确”。
            val data = decodeBase64Url(root.string("data"), 0, "加密凭据", MAX_RESPONSE_BYTES)
            if (data.isEmpty()) throw DesktopTransferException("电脑端返回的凭据为空")
            val expiresAt = root.long("expires_at")
            if (expiresAt != params.expiresAt) {
                throw DesktopTransferException("二维码有效期不一致，请重新生成")
            }
            return TransferResponse(nonce, data, expiresAt)
        }
    }

    private fun decrypt(params: TransferParams, response: TransferResponse): ByteArray {
        val aad = (AAD_PREFIX + "|" + params.token + "|" + response.expiresAt).toByteArray(Charsets.UTF_8)
        return try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                SecretKeySpec(params.key, "AES"),
                GCMParameterSpec(128, response.nonce)
            )
            cipher.updateAAD(aad)
            cipher.doFinal(response.data)
        } catch (_: Exception) {
            throw DesktopTransferException("登录凭据解密失败，二维码可能已失效")
        }
    }

    private fun parseCredential(plaintext: ByteArray): DesktopLoginCandidate {
        val root = try {
            json.parseToJsonElement(String(plaintext, Charsets.UTF_8)).jsonObject
        } catch (_: Exception) {
            throw DesktopTransferException("登录凭据内容无法解析")
        }
        if (root.string("schema") != "fusion-login-transfer") {
            throw DesktopTransferException("不支持的登录凭据格式")
        }
        if (root.int("version") != VERSION) {
            throw DesktopTransferException("登录凭据版本不匹配")
        }
        if (root.string("provider") != "netease") {
            throw DesktopTransferException("二维码不是网易云登录凭据")
        }
        val credential = root.obj("credential")
            ?: throw DesktopTransferException("二维码里没有登录凭据")
        if (credential.string("provider") != "netease") {
            throw DesktopTransferException("凭据来源不是网易云")
        }
        val cookies = credential.string("cookies")
        if (!hasMusicU(cookies)) {
            throw DesktopTransferException("二维码里没有有效的 MUSIC_U，请在电脑上重新登录")
        }
        val expiresAt = credential.long("expires_at")
        if (expiresAt > 0 && expiresAt < System.currentTimeMillis() / 1000L) {
            throw DesktopTransferException("电脑端的登录凭据已经过期，请先重新登录")
        }
        return DesktopLoginCandidate(
            cookies = cookies,
            userId = credential.long("user_id"),
            nickname = credential.string("nickname"),
            expiresAt = expiresAt,
            credential = credential
        )
    }

    private fun hasMusicU(cookie: String): Boolean {
        return cookie.split(';').any { part ->
            val item = part.trim()
            item.startsWith("MUSIC_U=") && item.substringAfter('=', "").isNotBlank()
        }
    }

    private fun isPrivateIpv4(host: String): Boolean {
        val parts = host.split('.')
        if (parts.size != 4) return false
        val numbers = parts.map { it.toIntOrNull() ?: return false }
        if (numbers.any { it !in 0..255 }) return false
        val a = numbers[0]
        val b = numbers[1]
        return a == 10 ||
            (a == 172 && b in 16..31) ||
            (a == 192 && b == 168) ||
            (a == 169 && b == 254)
    }

    private fun decodeBase64Url(
        value: String,
        expectedLength: Int,
        label: String,
        maxLength: Int = 512
    ): ByteArray {
        val text = value.trim()
        if (text.isEmpty() || text.length > maxLength) throw DesktopTransferException(label + "格式不正确")
        if (!text.matches(Regex("[A-Za-z0-9_-]+"))) throw DesktopTransferException(label + "格式不正确")
        val decoded = try {
            Base64.getUrlDecoder().decode(text + "=".repeat((4 - text.length % 4) % 4))
        } catch (_: Exception) {
            throw DesktopTransferException(label + "格式不正确")
        }
        if (expectedLength > 0 && decoded.size != expectedLength) {
            throw DesktopTransferException(label + "长度不正确")
        }
        return decoded
    }

    private fun encodeBase64Url(value: ByteArray): String {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value)
    }

    private fun readLimited(stream: java.io.InputStream): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        var total = 0
        while (true) {
            val count = stream.read(buffer)
            if (count <= 0) break
            total += count
            if (total > MAX_RESPONSE_BYTES) throw DesktopTransferException("电脑端返回的数据过大")
            output.write(buffer, 0, count)
        }
        return output.toByteArray()
    }
}
