package com.fusionlab.fusionmusic.data.net

import kotlinx.serialization.json.JsonObject
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.SecretKeySpec
import kotlin.random.Random

object Crypto {
    private val random = SecureRandom()
    private val base62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

    fun md5(text: String): String = digest("MD5", text.toByteArray(Charsets.UTF_8))

    fun sha1(text: String): String = digest("SHA-1", text.toByteArray(Charsets.UTF_8))

    fun sha256(text: String): String = digest("SHA-256", text.toByteArray(Charsets.UTF_8))

    fun md5Bytes(bytes: ByteArray): ByteArray = MessageDigest.getInstance("MD5").digest(bytes)

    fun sha256Bytes(bytes: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(bytes)

    fun hex(bytes: ByteArray): String = bytes.joinToString("") { byte -> "%02x".format(byte.toInt() and 0xFF) }

    fun hexUpper(bytes: ByteArray): String = hex(bytes).uppercase()

    fun base64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)

    fun aesEcb(data: ByteArray, key: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/ECB/PKCS5Padding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"))
        return cipher.doFinal(data)
    }

    fun aesCbc(data: ByteArray, key: ByteArray, iv: ByteArray): ByteArray {
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"), IvParameterSpec(iv))
        return cipher.doFinal(data)
    }

    fun rsaEncrypt(data: ByteArray): ByteArray {
        val cleaned = WY_PUBLIC_KEY
            .replace("-----BEGIN PUBLIC KEY-----", "")
            .replace("-----END PUBLIC KEY-----", "")
            .filterNot { it.isWhitespace() }
        val keyBytes = Base64.getDecoder().decode(cleaned)
        val publicKey = KeyFactory.getInstance("RSA").generatePublic(X509EncodedKeySpec(keyBytes))
        val cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding")
        cipher.init(Cipher.ENCRYPT_MODE, publicKey)
        return cipher.doFinal(data)
    }

    fun randomBase62(length: Int): String {
        val builder = StringBuilder(length)
        repeat(length) { builder.append(base62[Random.nextInt(base62.length)]) }
        return builder.toString()
    }

    fun randomHex(length: Int): String {
        val builder = StringBuilder(length)
        repeat(length) { builder.append("0123456789abcdef"[Random.nextInt(16)]) }
        return builder.toString()
    }

    fun wyWeapi(data: JsonObject): Map<String, String> {
        val text = data.toString()
        val secretKey = randomBase62(16).toByteArray(Charsets.UTF_8)
        val first = aesCbc(text.toByteArray(Charsets.UTF_8), WY_PRESET_KEY, WY_IV)
        val second = aesCbc(first, secretKey, WY_IV)
        val encSecKey = hex(rsaEncrypt(secretKey.reversedArray()))
        return mapOf("params" to base64(second), "encSecKey" to encSecKey)
    }

    fun wyEapi(url: String, data: JsonObject): Map<String, String> {
        val text = data.toString()
        val message = "nobody" + url + "use" + text + "md5forencrypt"
        val digest = md5(message)
        val raw = url + "-36cd479b6b5-" + text + "-36cd479b6b5-" + digest
        val encrypted = aesEcb(raw.toByteArray(Charsets.UTF_8), WY_EAPI_KEY)
        return mapOf("params" to hexUpper(encrypted))
    }

    fun wyLinuxapi(data: JsonObject): Map<String, String> {
        val text = data.toString()
        val encrypted = aesEcb(text.toByteArray(Charsets.UTF_8), WY_LINUXAPI_KEY)
        return mapOf("eparams" to hexUpper(encrypted))
    }

    fun txZzcSign(text: String): String {
        val hash = sha1(text)
        val part1 = PART1_IDX.joinToString("") { index -> if (index < hash.length) hash[index].toString() else "" }
        val part2 = PART2_IDX.joinToString("") { index -> if (index < hash.length) hash[index].toString() else "" }
        val part3 = ByteArray(20) { index ->
            val value = hash.substring(index * 2, index * 2 + 2).toInt(16)
            (SCRAMBLE[index] xor value).toByte()
        }
        val b64 = base64(part3).replace("/", "").replace("+", "").replace("=", "")
        return ("zzc" + part1 + b64 + part2).lowercase()
    }

    fun mgCreateSign(timestamp: Long, keyword: String): String {
        return md5(keyword + MG_SIGN_KEY + "yyapp2d16148780a1dcc7408e06336b98cfd50" + MG_DEVICE_ID + timestamp)
    }

    fun biliWbiSign(params: Map<String, String>, imgKey: String, subKey: String): Map<String, String> {
        val mixinKey = mixinKey(imgKey + subKey)
        val sorted = params.toSortedMap()
        val filtered = sorted.mapValues { (_, value) -> value.filterNot { ch -> "!'()*".contains(ch) } }
        val timestamp = System.currentTimeMillis() / 1000L
        val query = filtered.entries.joinToString("&") { (key, value) ->
            encode(key) + "=" + encode(value)
        } + "&wts=" + timestamp
        val wRid = md5(query + mixinKey)
        val result = LinkedHashMap(filtered)
        result["wts"] = timestamp.toString()
        result["w_rid"] = wRid
        return result
    }

    fun decodeName(raw: String): String {
        if (raw.isEmpty()) return raw
        if (!raw.startsWith("&#")) return raw
        var text = raw
        text = text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&#39;", "'")
            .replace("&apos;", "'")
        text = text.replace(Regex("&#x([0-9a-fA-F]+);")) { match ->
            codepoint(match.groupValues[1].toInt(16))
        }
        text = text.replace(Regex("&#([0-9]+);")) { match ->
            codepoint(match.groupValues[1].toIntOrNull() ?: 0)
        }
        return text
    }

    fun formatSinger(raw: String): String {
        if (raw.isEmpty()) return ""
        return raw.replace("&", "、").replace(";", "、").replace("/", "、")
    }

    private fun codepoint(value: Int): String {
        if (value <= 0) return ""
        return try {
            String(Character.toChars(value))
        } catch (_: Exception) {
            ""
        }
    }

    private fun mixinKey(raw: String): String {
        if (raw.length < 64) return raw
        val builder = StringBuilder(32)
        for (index in MIXIN_KEY_ENC_TAB) {
            builder.append(raw[index])
        }
        return builder.toString().substring(0, 32)
    }

    private fun encode(value: String): String {
        return java.net.URLEncoder.encode(value, "UTF-8")
            .replace("+", "%20")
            .replace("*", "%2A")
            .replace("%7E", "~")
    }

    private fun digest(algorithm: String, data: ByteArray): String {
        return hex(MessageDigest.getInstance(algorithm).digest(data))
    }

    const val WY_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDgtQn2JZ34ZC28NWYpAUd98iZ3
7BUrX/aKzmFbt7clFSs6sXqHauqKWqdtLkF2KexO40H1YTX8z2lSgBBOAxLsvakl
V8k4cBFK9snQXE9/DDaFt6Rr7iVZMldczhC0JNgTz+SHXT6CBHuX3e9SdB1Ua44o
ncaTWz7OBGLbCiK45wIDAQAB
-----END PUBLIC KEY-----"""

    private val WY_EAPI_KEY = "e82ckenh8dichen8".toByteArray(Charsets.UTF_8)
    private val WY_PRESET_KEY = "0CoJUm6Qyw8W8jud".toByteArray(Charsets.UTF_8)
    private val WY_IV = "0102030405060708".toByteArray(Charsets.UTF_8)
    private val WY_LINUXAPI_KEY = "rFgB&h#%2?^eDg:Q".toByteArray(Charsets.UTF_8)

    private val PART1_IDX = intArrayOf(23, 14, 6, 36, 16, 40, 7, 19)
    private val PART2_IDX = intArrayOf(16, 1, 32, 12, 19, 27, 8, 5)
    private val SCRAMBLE = intArrayOf(89, 39, 179, 150, 218, 82, 58, 252, 177, 52, 186, 123, 120, 64, 242, 133, 143, 161, 121, 179)
    private const val MG_DEVICE_ID = "963B7AA0D21511ED807EE5846EC87D20"
    private const val MG_SIGN_KEY = "6cdc72a439cef99a3418d2a78aa28c73"
    private val MIXIN_KEY_ENC_TAB = intArrayOf(
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
        33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
        61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
        36, 20, 34, 44, 52
    )
}
