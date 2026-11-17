package com.fusionlab.fusionmusic.data.account

import android.content.Context
import com.fusionlab.fusionmusic.BuildConfig
import com.fusionlab.fusionmusic.core.util.AppLog
import com.fusionlab.fusionmusic.data.config.ConfigRepository
import com.fusionlab.fusionmusic.data.source.NeteaseSource
import com.fusionlab.fusionmusic.data.source.SourceRegistry
import com.fusionlab.fusionmusic.security.CredentialVault
import com.fusionlab.fusionmusic.security.VaultException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import java.util.concurrent.TimeUnit

data class AccountState(
    val loggedIn: Boolean = false,
    val busy: Boolean = false,
    val status: String = "未登录",
    val nickname: String = "",
    val avatarUrl: String = "",
    val userId: Long = 0L,
    val vipLabel: String = "",
    val vipDetail: String = "",
    val remotePlaylists: List<NeteaseSource.RemotePlaylist> = emptyList(),
    val portable: Boolean = false,
    val keySource: String = "",
    val daysLeft: Int = 0,
    val error: String? = null
)

class AccountRepository(
    context: Context,
    private val config: ConfigRepository,
    private val sources: SourceRegistry,
    private val log: AppLog,
    private val scope: CoroutineScope
) {
    private val vault = CredentialVault(context, config)
    private val state = MutableStateFlow(AccountState())
    val snapshot: StateFlow<AccountState> = state

    private val source: NeteaseSource?
        get() = sources.getSource("wy") as? NeteaseSource

    init {
        state.value = state.value.copy(portable = vault.portable(), keySource = vault.keySource())
        scope.launch { restore() }
        scope.launch {
            while (isActive) {
                delay(6L * 60L * 60L * 1000L)
                if (state.value.loggedIn) {
                    try {
                        renewIfNeeded()
                    } catch (error: Exception) {
                        log.w("Account", "periodic renew failed: " + error.message)
                    }
                }
            }
        }
    }

    fun setError(message: String) = update { it.copy(error = message) }

    fun clearError() = update { it.copy(error = null) }

    suspend fun restore() = withContext(Dispatchers.IO) {
        if (!config.getBoolean("account.auto_login", true)) {
            update { it.copy(status = "未登录", busy = false) }
            return@withContext
        }
        val payload = try {
            vault.load()
        } catch (error: VaultException) {
            update { it.copy(status = "凭据不可用", error = error.message, busy = false) }
            return@withContext
        } catch (error: Exception) {
            log.w("Account", "load credentials failed: " + error.message)
            null
        }
        if (payload == null) {
            update { it.copy(status = "未登录", busy = false, keySource = vault.keySource(), portable = vault.portable()) }
            return@withContext
        }
        if (payload["provider"]?.jsonPrimitive?.content != "netease") {
            update { it.copy(status = "未登录", busy = false) }
            return@withContext
        }
        val cookies = payload["cookies"]?.jsonPrimitive?.content ?: ""
        if (cookies.isBlank()) {
            update { it.copy(status = "未登录", busy = false) }
            return@withContext
        }
        val netease = source ?: return@withContext
        netease.applyCookie(cookies)
        if (!netease.isLoggedIn()) {
            update { it.copy(status = "凭据已失效，请重新登录", busy = false) }
            return@withContext
        }
        val expiresAt = payload["expires_at"]?.jsonPrimitive?.content?.toLongOrNull() ?: 0L
        val profile = try {
            netease.fetchProfile()
        } catch (error: Exception) {
            log.w("Account", "profile failed: " + error.message)
            null
        }
        update {
            it.copy(
                loggedIn = true,
                busy = false,
                status = "已登录",
                nickname = profile?.nickname ?: payload["nickname"]?.jsonPrimitive?.content.orEmpty(),
                avatarUrl = profile?.avatarUrl ?: payload["avatar_url"]?.jsonPrimitive?.content.orEmpty(),
                userId = profile?.userId ?: (payload["user_id"]?.jsonPrimitive?.content?.toLongOrNull() ?: 0L),
                vipLabel = vipLabel(profile, payload),
                vipDetail = vipDetail(profile, payload),
                daysLeft = daysLeft(expiresAt),
                portable = vault.portable(),
                keySource = vault.keySource()
            )
        }
        if (profile != null) saveCredentials(profile, cookies, expiresAt)
        renewIfNeeded()
        refreshPlaylists()
    }

    suspend fun startQrLogin(): String? = withContext(Dispatchers.IO) {
        update { it.copy(busy = true, status = "正在获取二维码…", error = null) }
        val netease = source
        if (netease == null) {
            fail("音源不可用")
            return@withContext null
        }
        val key = try {
            netease.loginQrKey()
        } catch (error: Exception) {
            log.w("Account", "qr key failed: " + error.message)
            null
        }
        if (key == null) {
            fail("无法获取二维码，请检查网络后重试")
            return@withContext null
        }
        update { it.copy(status = "请使用网易云音乐 App 扫描二维码") }
        key
    }

    suspend fun pollQr(key: String): NeteaseSource.QrCheck? = withContext(Dispatchers.IO) {
        val netease = source ?: return@withContext null
        val check = try {
            netease.loginQrCheck(key)
        } catch (error: Exception) {
            log.w("Account", "qr poll failed: " + error.message)
            return@withContext null
        }
        when (check.code) {
            802 -> update { it.copy(status = "扫描成功，请在手机上确认登录") }
            801 -> update { it.copy(status = "等待扫码…") }
            800 -> update { it.copy(status = "二维码已失效", busy = false) }
            803 -> {
                if (netease.isLoggedIn()) onLoggedIn(netease.cookieString()) else fail("授权成功但未取到登录凭据")
            }
        }
        check
    }

    suspend fun sendCaptcha(phone: String, countryCode: String = "86"): Boolean = withContext(Dispatchers.IO) {
        if (phone.isBlank()) return@withContext false
        val netease = source ?: return@withContext false
        update { it.copy(busy = true, status = "正在发送验证码…", error = null) }
        val response = netease.eapi(
            "/api/sms/captcha/sent",
            JsonObject(
                linkedMapOf(
                    "cellphone" to JsonPrimitive(phone),
                    "ctcode" to JsonPrimitive(countryCode.ifBlank { "86" })
                )
            )
        )
        val ok = response?.get("code")?.jsonPrimitive?.content?.toIntOrNull() == 200
        if (ok) update { it.copy(status = "验证码已发送", busy = false) } else fail("验证码发送失败")
        ok
    }

    suspend fun loginWithPhone(
        phone: String,
        secret: String,
        countryCode: String = "86",
        usePassword: Boolean = false
    ): Boolean = withContext(Dispatchers.IO) {
        if (phone.isBlank() || secret.isBlank()) return@withContext false
        val netease = source ?: return@withContext false
        update { it.copy(busy = true, status = "正在登录…", error = null) }
        val data = linkedMapOf<String, JsonPrimitive>(
            "phone" to JsonPrimitive(phone),
            "countrycode" to JsonPrimitive(countryCode.ifBlank { "86" }),
            "rememberLogin" to JsonPrimitive(true)
        )
        if (usePassword) data["password"] = JsonPrimitive(secret) else data["captcha"] = JsonPrimitive(secret)
        val response = netease.eapi("/api/login/cellphone", JsonObject(data))
        val code = response?.get("code")?.jsonPrimitive?.content?.toIntOrNull()
        if (code != 200) {
            fail(response?.get("message")?.jsonPrimitive?.content ?: "登录失败")
            return@withContext false
        }
        if (!netease.isLoggedIn()) {
            fail("登录响应成功但未获取到登录凭据")
            return@withContext false
        }
        onLoggedIn(netease.cookieString())
        true
    }

    suspend fun loginWithCookie(cookie: String): Boolean = withContext(Dispatchers.IO) {
        val text = cookie.trim()
        if (text.isEmpty()) return@withContext false
        val netease = source ?: return@withContext false
        update { it.copy(busy = true, status = "正在校验 Cookie…", error = null) }
        netease.applyCookie(text)
        if (!netease.isLoggedIn()) {
            fail("Cookie 无效：没有找到 MUSIC_U")
            return@withContext false
        }
        onLoggedIn(netease.cookieString())
        true
    }

    suspend fun prepareDesktopLogin(uri: String): DesktopLoginCandidate? = withContext(Dispatchers.IO) {
        update { it.copy(busy = true, status = "正在读取桌面登录信息…", error = null) }
        try {
            val candidate = DesktopLoginTransfer.redeem(uri, log)
            update { it.copy(busy = false, status = "扫描成功", error = null) }
            candidate
        } catch (error: DesktopTransferException) {
            failDesktop(error.message ?: "无法读取桌面登录信息")
            null
        } catch (error: Exception) {
            log.w("Account", "desktop transfer failed: " + error.javaClass.simpleName)
            failDesktop("读取桌面登录信息失败")
            null
        }
    }

    suspend fun applyDesktopLogin(candidate: DesktopLoginCandidate): Boolean = withContext(Dispatchers.IO) {
        val netease = source
        if (netease == null) {
            failDesktop("音源不可用，请稍后重试")
            return@withContext false
        }
        update { it.copy(busy = true, status = "正在验证桌面登录…", error = null) }
        val previousCookie = netease.cookieString()
        val previousLoggedIn = currentLoggedIn()
        try {
            netease.applyCookie(candidate.cookies)
            if (!netease.isLoggedIn()) {
                throw DesktopTransferException("二维码里的 MUSIC_U 无效，请在电脑上重新登录")
            }
            val profile = netease.fetchProfile()
                ?: throw DesktopTransferException("无法验证桌面登录，请检查网络后重试")
            if (candidate.userId > 0 && profile.userId > 0 && candidate.userId != profile.userId) {
                throw DesktopTransferException("登录账号与电脑端不一致，请重新扫码")
            }
            val now = System.currentTimeMillis() / 1000L
            val expiry = if (candidate.expiresAt > now) {
                candidate.expiresAt
            } else {
                netease.cookieExpiry() ?: (now + TTL_SECONDS)
            }
            val cookies = netease.cookieString().ifBlank { candidate.cookies }
            val saveWarning = saveImportedCredentials(profile, cookies, expiry, candidate)
            val merged = importedPayload(candidate, profile, cookies, expiry)
            update {
                it.copy(
                    loggedIn = true,
                    busy = false,
                    status = "已登录",
                    nickname = profile.nickname.ifBlank { candidate.nickname },
                    avatarUrl = profile.avatarUrl,
                    userId = profile.userId,
                    vipLabel = vipLabel(profile, merged),
                    vipDetail = vipDetail(profile, merged),
                    daysLeft = daysLeft(expiry),
                    portable = vault.portable(),
                    keySource = vault.keySource(),
                    error = saveWarning
                )
            }
            refreshPlaylists()
            true
        } catch (error: DesktopTransferException) {
            restoreDesktopSession(netease, previousCookie, previousLoggedIn)
            failDesktop(error.message ?: "导入桌面登录失败")
            false
        } catch (error: Exception) {
            log.w("Account", "apply desktop login failed: " + error.javaClass.simpleName)
            restoreDesktopSession(netease, previousCookie, previousLoggedIn)
            failDesktop("导入桌面登录失败，请重试")
            false
        }
    }

    private fun saveImportedCredentials(
        profile: NeteaseSource.NeteaseProfile,
        cookies: String,
        expiresAt: Long,
        candidate: DesktopLoginCandidate
    ): String? {
        if (!config.getBoolean("account.save_credentials", true)) return null
        return try {
            val saved = vault.save(importedPayload(candidate, profile, cookies, expiresAt))
            if (saved) null else "登录成功，但凭据保存失败"
        } catch (error: Exception) {
            log.w("Account", "save desktop credentials failed: " + error.javaClass.simpleName)
            error.message ?: "登录成功，但凭据保存失败"
        }
    }

    private fun importedPayload(
        candidate: DesktopLoginCandidate,
        profile: NeteaseSource.NeteaseProfile,
        cookies: String,
        expiresAt: Long
    ): JsonObject {
        val payload = LinkedHashMap<String, JsonElement>(candidate.credential)
        payload["provider"] = JsonPrimitive("netease")
        payload["cookies"] = JsonPrimitive(cookies)
        payload["user_id"] = JsonPrimitive(profile.userId)
        payload["nickname"] = JsonPrimitive(profile.nickname)
        payload["avatar_url"] = JsonPrimitive(profile.avatarUrl)
        payload["vip_type"] = JsonPrimitive(profile.vipType)
        payload["has_music_package"] = JsonPrimitive(profile.hasMusicPackage)
        payload["red_vip_level"] = JsonPrimitive(profile.redVipLevel)
        payload["obtained_at"] = JsonPrimitive(System.currentTimeMillis() / 1000L)
        payload["expires_at"] = JsonPrimitive(expiresAt)
        payload["app_version"] = JsonPrimitive(BuildConfig.APP_VERSION)
        payload["imported_from"] = JsonPrimitive("desktop")
        return JsonObject(payload)
    }

    private fun restoreDesktopSession(
        netease: NeteaseSource,
        previousCookie: String,
        previousLoggedIn: Boolean
    ) {
        try {
            if (previousLoggedIn && previousCookie.isNotBlank()) {
                netease.applyCookie(previousCookie)
            } else {
                netease.clearLogin()
            }
        } catch (error: Exception) {
            log.w("Account", "restore previous session failed: " + error.javaClass.simpleName)
        }
    }

    private fun currentLoggedIn(): Boolean = state.value.loggedIn

    private fun failDesktop(message: String) {
        update {
            it.copy(
                busy = false,
                status = if (it.loggedIn) "已登录" else "未登录",
                error = message
            )
        }
    }

    suspend fun renewIfNeeded(): Boolean = withContext(Dispatchers.IO) {
        val current = state.value
        if (!current.loggedIn) return@withContext false
        val refreshDays = config.getInt("account.cookie_refresh_days", 7)
        if (refreshDays <= 0) return@withContext false
        val remaining = current.daysLeft
        if (remaining > refreshDays) return@withContext false
        val netease = source ?: return@withContext false
        val renewed = try {
            netease.refreshLogin()
        } catch (_: Exception) {
            null
        }
        if (renewed.isNullOrBlank()) return@withContext false
        val profile = try {
            netease.fetchProfile()
        } catch (_: Exception) {
            null
        }
        val expiry = netease.cookieExpiry() ?: (System.currentTimeMillis() / 1000L + TTL_SECONDS)
        if (profile != null) saveCredentials(profile, renewed, expiry)
        update { it.copy(daysLeft = daysLeft(expiry)) }
        true
    }

    fun refreshPlaylists() {
        scope.launch {
            val netease = source ?: return@launch
            if (!netease.isLoggedIn()) return@launch
            val playlists = try {
                netease.userPlaylists()
            } catch (error: Exception) {
                log.w("Account", "playlists failed: " + error.message)
                null
            }
            if (playlists != null) update { it.copy(remotePlaylists = playlists) }
        }
    }

    suspend fun logout() = withContext(Dispatchers.IO) {
        source?.clearLogin()
        vault.clear()
        update {
            AccountState(
                status = "未登录",
                portable = vault.portable(),
                keySource = vault.keySource()
            )
        }
    }

    fun setPortable(enabled: Boolean) {
        try {
            vault.setPortable(enabled)
            update { it.copy(portable = vault.portable(), keySource = vault.keySource()) }
        } catch (error: Exception) {
            update { it.copy(error = error.message) }
        }
    }

    fun rebuildKey(): Boolean {
        val ok = vault.rebuildKey()
        update {
            it.copy(
                loggedIn = false,
                status = if (ok) "密钥已重建，请重新登录" else "密钥重建失败",
                error = if (ok) null else "无法重建密钥",
                portable = vault.portable(),
                keySource = vault.keySource()
            )
        }
        return ok
    }

    fun credentialDaysLeft(): Int = state.value.daysLeft

    fun keySource(): String = vault.keySource()

    fun keyUsable(): Boolean = vault.keyUsable()

    private fun onLoggedIn(cookie: String) {
        val netease = source ?: return
        if (!netease.isLoggedIn()) {
            fail("登录失败：未取到登录凭据")
            return
        }
        val profile = try {
            netease.fetchProfile()
        } catch (_: Exception) {
            null
        }
        val expiry = netease.cookieExpiry() ?: (System.currentTimeMillis() / 1000L + TTL_SECONDS)
        update {
            it.copy(
                loggedIn = true,
                busy = false,
                status = "已登录",
                nickname = profile?.nickname.orEmpty(),
                avatarUrl = profile?.avatarUrl.orEmpty(),
                userId = profile?.userId ?: 0L,
                vipLabel = vipLabel(profile, null),
                vipDetail = vipDetail(profile, null),
                daysLeft = daysLeft(expiry),
                error = null
            )
        }
        if (profile != null) saveCredentials(profile, cookie, expiry)
        refreshPlaylists()
    }

    private fun saveCredentials(profile: NeteaseSource.NeteaseProfile, cookies: String, expiresAt: Long) {
        if (!config.getBoolean("account.save_credentials", true)) return
        if (cookies.isBlank()) return
        val payload = JsonObject(
            linkedMapOf(
                "provider" to JsonPrimitive("netease"),
                "cookies" to JsonPrimitive(cookies),
                "user_id" to JsonPrimitive(profile.userId),
                "nickname" to JsonPrimitive(profile.nickname),
                "avatar_url" to JsonPrimitive(profile.avatarUrl),
                "vip_type" to JsonPrimitive(profile.vipType),
                "has_music_package" to JsonPrimitive(profile.hasMusicPackage),
                "red_vip_level" to JsonPrimitive(profile.redVipLevel),
                "obtained_at" to JsonPrimitive(System.currentTimeMillis() / 1000L),
                "expires_at" to JsonPrimitive(expiresAt),
                "app_version" to JsonPrimitive(BuildConfig.APP_VERSION)
            )
        )
        try {
            vault.save(payload)
        } catch (error: Exception) {
            update { it.copy(error = error.message ?: "凭据保存失败") }
        }
    }

    private fun vipLabel(profile: NeteaseSource.NeteaseProfile?, payload: JsonObject?): String {
        val type = profile?.vipType ?: payload?.get("vip_type")?.jsonPrimitive?.content?.toIntOrNull() ?: 0
        val musicPackage = profile?.hasMusicPackage
            ?: payload?.get("has_music_package")?.jsonPrimitive?.content?.toBooleanStrictOrNull()
            ?: false
        val level = profile?.redVipLevel ?: payload?.get("red_vip_level")?.jsonPrimitive?.content?.toIntOrNull() ?: 0
        return when {
            type == 20 || type == 300 -> "黑胶SVIP" + levelSuffix(level)
            type == 10 || type == 11 || type == 100 || (type and 10) == 10 -> "黑胶VIP"
            musicPackage || type == 1 || type == 220 -> "音乐包"
            else -> "普通用户"
        }
    }

    private fun vipDetail(profile: NeteaseSource.NeteaseProfile?, payload: JsonObject?): String {
        val type = profile?.vipType ?: payload?.get("vip_type")?.jsonPrimitive?.content?.toIntOrNull() ?: 0
        val level = profile?.redVipLevel ?: payload?.get("red_vip_level")?.jsonPrimitive?.content?.toIntOrNull() ?: 0
        val parts = mutableListOf<String>()
        val label = vipLabel(profile, payload)
        if (label != "普通用户") parts.add(label)
        if (level > 0) parts.add("等级 Lv" + level)
        if (parts.isEmpty()) parts.add("无会员权益")
        return parts.joinToString(" · ") + "（vipType=" + type + "）"
    }

    private fun levelSuffix(level: Int): String {
        if (level <= 0) return ""
        if (level > 99) return "·" + level
        val digits = listOf("零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖")
        return if (level < 10) "·" + digits[level] else "·" + (if (level / 10 == 1) "拾" else digits[level / 10] + "拾") + (if (level % 10 == 0) "" else digits[level % 10])
    }

    private fun daysLeft(expiresAt: Long): Int {
        if (expiresAt <= 0) return 0
        val now = System.currentTimeMillis() / 1000L
        return ((expiresAt - now) / TimeUnit.DAYS.toSeconds(1)).toInt().coerceAtLeast(0)
    }

    private fun fail(message: String) {
        update { it.copy(busy = false, status = "未登录", error = message) }
    }

    private fun update(block: (AccountState) -> AccountState) {
        state.value = block(state.value)
    }

    companion object {
        private const val TTL_SECONDS = 180L * 24L * 3600L
    }
}
