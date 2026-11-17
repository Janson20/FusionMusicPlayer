package com.fusionlab.fusionmusic.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.io.FileOutputStream
import java.security.KeyStore
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.Mac
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

class VaultException(message: String, cause: Throwable? = null) : RuntimeException(message, cause)

class CredentialVault(
    context: Context,
    private val config: ConfigRepository
) {
    private val dataDir = File(context.filesDir, "data").apply { mkdirs() }
    private val keyDir = File(dataDir, "keys").apply { mkdirs() }
    private val file = File(dataDir, "credentials.enc")
    private val keyFile = File(keyDir, "master.key")
    private val json = Json { prettyPrint = true; prettyPrintIndent = "  " }
    private val random = SecureRandom()
    private val lock = Any()

    fun exists(): Boolean = file.exists()

    fun portable(): Boolean = config.getBoolean("account.portable", false)

    fun keySource(): String = if (portable()) "portable" else "keystore"

    fun load(): JsonObject? = synchronized(lock) {
        if (!file.exists()) return null
        try {
            val envelope = json.parseToJsonElement(file.readText(Charsets.UTF_8)).jsonObject
            if (envelope["format_version"]?.jsonPrimitive?.content?.toIntOrNull() != FORMAT_VERSION) {
                throw VaultException("不支持的凭据文件版本")
            }
            if (envelope["cipher"]?.jsonPrimitive?.content != CIPHER) {
                throw VaultException("不支持的加密算法")
            }
            val nonce = Base64.getDecoder().decode(envelope["nonce"]?.jsonPrimitive?.content ?: "")
            val payload = Base64.getDecoder().decode(envelope["payload"]?.jsonPrimitive?.content ?: "")
            val meta = metaOf(envelope)
            val aad = json.encodeToString(JsonObject.serializer(), meta).toByteArray(Charsets.UTF_8)
            val cipher = if (portable()) {
                val salt = Base64.getDecoder().decode(envelope["salt"]?.jsonPrimitive?.content ?: "")
                val key = derivePortableKey(salt)
                Cipher.getInstance("AES/GCM/NoPadding").apply {
                    init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, nonce))
                    updateAAD(aad)
                }
            } else {
                val key = keystoreKey(false) ?: throw VaultException("Android Keystore 中没有凭据密钥")
                Cipher.getInstance("AES/GCM/NoPadding").apply {
                    init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, nonce))
                    updateAAD(aad)
                }
            }
            val plaintext = cipher.doFinal(payload)
            json.parseToJsonElement(String(plaintext, Charsets.UTF_8)).jsonObject
        } catch (error: VaultException) {
            throw error
        } catch (error: Exception) {
            throw VaultException("凭据解密失败（密钥不匹配或文件损坏）", error)
        }
    }

    fun save(payload: JsonObject): Boolean = synchronized(lock) {
        try {
            val salt = if (portable()) randomBytes(32) else ByteArray(0)
            val nonce = randomBytes(12)
            val keySource = if (portable()) "portable" else "keystore"
            val meta = linkedMapOf<String, kotlinx.serialization.json.JsonElement>(
                "format_version" to JsonPrimitive(FORMAT_VERSION),
                "cipher" to JsonPrimitive(CIPHER),
                "kdf" to JsonPrimitive(if (portable()) "hkdf-sha256" else "keystore"),
                "key_source" to JsonPrimitive(keySource),
                "salt" to JsonPrimitive(Base64.getEncoder().encodeToString(salt)),
                "nonce" to JsonPrimitive(Base64.getEncoder().encodeToString(nonce)),
                "saved_at" to JsonPrimitive(System.currentTimeMillis() / 1000L)
            )
            val aad = json.encodeToString(JsonObject.serializer(), JsonObject(meta)).toByteArray(Charsets.UTF_8)
            val cipher = if (portable()) {
                val key = derivePortableKey(salt)
                Cipher.getInstance("AES/GCM/NoPadding").apply {
                    init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(128, nonce))
                    updateAAD(aad)
                }
            } else {
                val key = keystoreKey(true) ?: throw VaultException("无法创建 Android Keystore 凭据密钥")
                Cipher.getInstance("AES/GCM/NoPadding").apply {
                    init(Cipher.ENCRYPT_MODE, key, GCMParameterSpec(128, nonce))
                    updateAAD(aad)
                }
            }
            val encrypted = cipher.doFinal(json.encodeToString(JsonObject.serializer(), payload).toByteArray(Charsets.UTF_8))
            val envelope = LinkedHashMap(meta)
            envelope["payload"] = JsonPrimitive(Base64.getEncoder().encodeToString(encrypted))
            writeAtomic(json.encodeToString(JsonObject.serializer(), JsonObject(envelope)))
            true
        } catch (error: VaultException) {
            throw error
        } catch (error: Exception) {
            throw VaultException("凭据加密保存失败", error)
        }
    }

    fun clear() {
        file.delete()
    }

    fun setPortable(enabled: Boolean): Boolean {
        val payload = load()
        config.setBoolean("account.portable", enabled)
        if (payload != null) save(payload)
        return true
    }

    fun keyUsable(): Boolean = try {
        if (portable()) {
            readPortableKey()
        } else {
            keystoreKey(false) != null
        }
        true
    } catch (_: Exception) {
        false
    }

    fun rebuildKey(): Boolean {
        try {
            if (keyFile.exists()) {
                val backup = File(keyFile.parentFile, keyFile.name + ".unreadable")
                if (backup.exists()) backup.delete()
                keyFile.renameTo(backup)
            }
            val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            if (keyStore.containsAlias(KEY_ALIAS)) keyStore.deleteEntry(KEY_ALIAS)
            file.delete()
            return true
        } catch (_: Exception) {
            return false
        }
    }

    private fun derivePortableKey(salt: ByteArray): SecretKey {
        val master = readPortableKey()
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(master, "HmacSHA256"))
        val prk = mac.doFinal(salt)
        mac.init(SecretKeySpec(prk, "HmacSHA256"))
        mac.update("FusionMusicPlayer/credentials/v1".toByteArray(Charsets.UTF_8))
        mac.update(byteArrayOf(0x01))
        val okm = mac.doFinal()
        return SecretKeySpec(okm.copyOf(32), "AES")
    }

    private fun readPortableKey(): ByteArray {
        if (!keyFile.exists()) {
            val raw = randomBytes(32)
            writeBytesAtomic(keyFile, PORTABLE_MAGIC + raw)
            return raw
        }
        val raw = keyFile.readBytes()
        return when {
            raw.size == 32 -> raw
            raw.size == 36 && raw.copyOfRange(0, 4).contentEquals(PORTABLE_MAGIC) -> raw.copyOfRange(4, 36)
            else -> throw VaultException("便携密钥文件已损坏")
        }
    }

    private fun keystoreKey(create: Boolean): SecretKey? {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (keyStore.containsAlias(KEY_ALIAS)) {
            return keyStore.getKey(KEY_ALIAS, null) as? SecretKey
        }
        if (!create) return null
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    private fun metaOf(envelope: JsonObject): JsonObject {
        val keys = listOf("format_version", "cipher", "kdf", "key_source", "salt", "nonce", "saved_at")
        val map = LinkedHashMap<String, kotlinx.serialization.json.JsonElement>()
        for (key in keys) {
            val value = envelope[key] ?: continue
            map[key] = value
        }
        return JsonObject(map)
    }

    private fun randomBytes(size: Int): ByteArray = ByteArray(size).also { random.nextBytes(it) }

    private fun writeAtomic(text: String) {
        val temp = File(file.parentFile, file.name + ".tmp")
        FileOutputStream(temp).use { stream ->
            stream.write(text.toByteArray(Charsets.UTF_8))
            stream.fd.sync()
        }
        if (file.exists()) file.delete()
        if (!temp.renameTo(file)) {
            temp.copyTo(file, overwrite = true)
            temp.delete()
        }
    }

    private fun writeBytesAtomic(target: File, bytes: ByteArray) {
        val temp = File(target.parentFile, target.name + ".tmp")
        FileOutputStream(temp).use { stream ->
            stream.write(bytes)
            stream.fd.sync()
        }
        if (target.exists()) target.delete()
        if (!temp.renameTo(target)) {
            temp.copyTo(target, overwrite = true)
            temp.delete()
        }
    }

    companion object {
        private const val FORMAT_VERSION = 1
        private const val CIPHER = "aes-256-gcm"
        private const val KEY_ALIAS = "fusion_credentials_key"
        private val PORTABLE_MAGIC = "PORT".toByteArray(Charsets.UTF_8)
    }
}
