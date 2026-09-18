"""网易云账号：登录 / 登出 / 凭据加密持久化。

登录方式
--------
* **扫码登录**（推荐，也是 FMCL 唯一实现的方式）：取 ``unikey`` → 本地渲染二维码
  → 轮询 ``800/801/802/803``。
* **手机号 + 短信验证码**：``/api/sms/captcha/sent`` → ``/api/login/cellphone``。
* **手机号 + 密码**：同一路由。注意网易已逐步下线密码登录，服务端可能返回
  ``code=502 请切换登录方式或升级版本``，此时应引导用户改用扫码或短信。
* **手动粘贴 Cookie**：把外部获取的 ``MUSIC_U`` 等 Cookie 直接交给音源会话。

凭据以 AES-256-GCM 认证加密后写入 ``<程序目录>/data/credentials.enc``，
密钥见 :mod:`app.security.vault`。**绝不在日志里打印 Cookie。**
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Property, Signal, Slot

from .. import paths
from ..paths import APP_VERSION
from ..security import vault
from ..security.vault import VaultError
from ..sources import (
    wy_apply_cookie,
    wy_clear_cookie,
    wy_fetch_profile,
    wy_get_cookie_str,
    wy_get_user_playlists,
    wy_is_logged_in,
    wy_login_qr_check,
    wy_login_qr_key,
    wy_source,
)

logger = logging.getLogger(__name__)

QR_URL_PREFIX = "https://music.163.com/login?codekey="
QR_POLL_INTERVAL = 1.5
QR_POLL_MAX_SECONDS = 300

# 网易云扫码状态码
QR_EXPIRED = 800
QR_WAIT_SCAN = 801
QR_SCANNED = 802
QR_SUCCESS = 803

PROVIDER = "netease"
MUSIC_U_TTL_SECONDS = 180 * 24 * 3600  # MUSIC_U 的 Max-Age 约 180 天

# 网易云会员标识（vipCode / vipType 位掩码都归一到这几个名字）
VIP_LABELS = {
    0: "普通用户",
    1: "音乐包",
    10: "黑胶VIP",
    11: "黑胶VIP",
    20: "黑胶SVIP",
    100: "黑胶VIP",
    220: "音乐包",
    300: "黑胶SVIP",
}

class _Emitter(QObject):
    qrReady = Signal(object)
    qrPoll = Signal(object)
    loginDone = Signal(object)
    profileDone = Signal(object)
    playlistsDone = Signal(object)

class AccountManager(QObject):
    """网易云账号状态与登录流程。"""

    qrChanged = Signal()
    statusChanged = Signal()
    loggedInChanged = Signal()
    profileChanged = Signal()
    playlistsChanged = Signal()
    busyChanged = Signal()
    message = Signal(str)
    errorOccurred = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._emitter = _Emitter(self)
        self._emitter.qrReady.connect(self._on_qr_ready)
        self._emitter.qrPoll.connect(self._on_qr_poll)
        self._emitter.loginDone.connect(self._on_login_done)
        self._emitter.profileDone.connect(self._on_profile_done)
        self._emitter.playlistsDone.connect(self._on_playlists_done)

        self._logged_in = False
        self._busy = False
        self._status = "未登录"
        self._qr_image = ""
        self._qr_key = ""
        self._qr_seq = 0
        self._qr_running = False

        self._nickname = ""
        self._avatar = ""
        self._user_id = 0
        self._vip_type = 0
        self._has_music_package = False
        self._has_black_vip = False
        self._is_svip = False
        self._red_vip_level = 0
        self._red_vip_annual_count = 0
        self._remote_playlists: list = []

    # ── 属性 ────────────────────────────────────────────────

    @Property(bool, notify=loggedInChanged)
    def loggedIn(self) -> bool:  # noqa: N802
        return self._logged_in

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(str, notify=qrChanged)
    def qrImage(self) -> str:  # noqa: N802
        return self._qr_image

    @Property(str, notify=profileChanged)
    def nickname(self) -> str:
        return self._nickname

    @Property(str, notify=profileChanged)
    def avatar(self) -> str:
        return self._avatar

    @Property(int, notify=profileChanged)
    def userId(self) -> int:  # noqa: N802
        return self._user_id

    @Property(str, notify=profileChanged)
    def vipLabel(self) -> str:  # noqa: N802
        if not self._logged_in:
            return ""
        if self._is_svip:
            label = VIP_LABELS[300]
            if self._red_vip_level > 0:
                label += f" Lv{self._red_vip_level}"
            return label
        if self._has_black_vip or (self._vip_type & 10) == 10 or self._vip_type in (10, 11):
            return VIP_LABELS[100]
        if self._has_music_package or (self._vip_type & 1) == 1 or self._vip_type == 1:
            return VIP_LABELS[220]
        return VIP_LABELS.get(self._vip_type, "普通用户")

    @Property(bool, notify=profileChanged)
    def isVip(self) -> bool:  # noqa: N802
        return self._is_svip or self._has_black_vip or self._has_music_package

    @Property(bool, notify=profileChanged)
    def isSvip(self) -> bool:  # noqa: N802
        return self._is_svip

    @Property(int, notify=profileChanged)
    def vipType(self) -> int:  # noqa: N802
        return self._vip_type

    @Property(str, notify=profileChanged)
    def vipDetail(self) -> str:  # noqa: N802
        """给设置页用的权益明细，方便排查识别问题。"""
        if not self._logged_in:
            return ""
        parts = []
        if self._is_svip:
            parts.append("黑胶SVIP")
        elif self._has_black_vip:
            parts.append("黑胶VIP")
        if self._has_music_package:
            parts.append("音乐包")
        if self._red_vip_level > 0:
            parts.append(f"等级 Lv{self._red_vip_level}")
        if self._red_vip_annual_count > 0:
            parts.append("年费")
        detail = " · ".join(parts) if parts else "无会员权益"
        return f"{detail}（vipType={self._vip_type}）"

    @Property("QVariantList", notify=playlistsChanged)
    def remotePlaylists(self):  # noqa: N802
        return self._remote_playlists

    @Property(bool, constant=True)
    def hasSavedCredentials(self) -> bool:  # noqa: N802
        return vault.exists()

    @Property(str, constant=True)
    def credentialPath(self) -> str:  # noqa: N802
        return str(paths.credentials_file())

    @Property(str, constant=True)
    def keySource(self) -> str:  # noqa: N802
        return vault.key_source()

    @Property(str, constant=True)
    def dataDir(self) -> str:  # noqa: N802
        return str(paths.data_dir())

    # ── 启动恢复 ────────────────────────────────────────────

    @Slot()
    def restore(self) -> None:
        """启动时用已保存的加密凭据恢复登录态，并做一次服务端校验。"""
        if not bool(self._config.get("account.auto_login", True)):
            self._set_status("未登录")
            return
        payload = None
        try:
            payload = vault.load()
        except VaultError as e:
            self.errorOccurred.emit(str(e))
            self._set_status("凭据不可用")
            return
        except Exception as e:
            logger.warning("读取凭据失败: %s", e)

        if not payload or payload.get("provider") != PROVIDER:
            self._set_status("未登录")
            return

        cookies = payload.get("cookies") or ""
        if not cookies:
            self._set_status("未登录")
            return

        if not wy_apply_cookie(cookies):
            self._set_status("未登录")
            return

        if not wy_is_logged_in():
            self._set_status("凭据已失效，请重新登录")
            return

        self._logged_in = True
        self._nickname = str(payload.get("nickname") or "")
        self._avatar = str(payload.get("avatar_url") or "")
        self._user_id = int(payload.get("user_id") or 0)
        self._apply_vip_fields(payload)
        self._set_status("已登录")
        self.loggedInChanged.emit()
        self.profileChanged.emit()
        logger.info("已从加密凭据恢复网易云登录态")

        # 服务端校验 + 拉取歌单（异步，不阻塞启动）
        threading.Thread(target=self._refresh_worker, daemon=True, name="wy-refresh").start()

    def _apply_vip_fields(self, profile: dict) -> None:
        """从（凭据或接口返回的）profile 里取出会员字段。

        ``is_svip`` / ``has_black_vip`` 由音源层依据权威接口
        ``/api/music-vip-membership/client/vip/info`` 的 vipCode 判定，
        这里只负责落库与派生。
        """
        self._vip_type = int(profile.get("vip_type") or 0)
        self._has_music_package = bool(profile.get("has_music_package"))
        self._has_black_vip = bool(profile.get("has_black_vip"))
        self._is_svip = bool(profile.get("is_svip"))
        self._red_vip_level = int(profile.get("red_vip_level") or 0)
        self._red_vip_annual_count = int(profile.get("red_vip_annual_count") or 0)

    # ── 扫码登录 ────────────────────────────────────────────

    @Slot()
    def startQrLogin(self) -> None:  # noqa: N802
        self._qr_seq += 1
        self._qr_running = True
        self._set_busy(True)
        self._set_status("正在获取二维码…")
        self._qr_image = ""
        self.qrChanged.emit()
        seq = self._qr_seq
        threading.Thread(target=self._qr_key_worker, args=(seq,), daemon=True, name="wy-qr-key").start()

    @Slot()
    def cancelQrLogin(self) -> None:  # noqa: N802
        self._qr_running = False
        self._qr_seq += 1
        self._set_busy(False)
        self._set_status("已取消")

    def _qr_key_worker(self, seq: int) -> None:
        try:
            key = wy_login_qr_key()
        except Exception as e:
            logger.warning("获取网易云二维码 unikey 失败: %s", e)
            key = None
        self._emitter.qrReady.emit((seq, key))

    @Slot(object)
    def _on_qr_ready(self, payload) -> None:
        seq, key = payload
        if seq != self._qr_seq or not self._qr_running:
            return
        if not key:
            self._set_busy(False)
            self._set_status("二维码获取失败")
            self.errorOccurred.emit("无法获取二维码，请检查网络后重试")
            return
        self._qr_key = key
        png = self._render_qr(key)
        if not png:
            self._set_busy(False)
            self._set_status("二维码生成失败")
            self.errorOccurred.emit("本地生成二维码失败（需要 qrcode 与 Pillow 依赖）")
            return
        from PySide6.QtCore import QUrl

        self._qr_image = QUrl.fromLocalFile(png).toString()
        self.qrChanged.emit()
        self._set_status("请使用网易云音乐 App 扫描二维码")
        threading.Thread(
            target=self._qr_poll_worker, args=(seq, key), daemon=True, name="wy-qr-poll"
        ).start()

    def _render_qr(self, key: str) -> Optional[str]:
        """本地把 ``https://music.163.com/login?codekey=<key>`` 渲染成 PNG。

        FMCL 同样使用本地渲染（不请求任何二维码图片接口）。
        """
        try:
            import qrcode

            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(f"{QR_URL_PREFIX}{key}")
            qr.make(fit=True)
            img = qr.make_image(fill_color="#14121F", back_color="white").convert("RGB")
            img = img.resize((260, 260))
            dest = paths.cache_dir() / "login" / "qr.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            img.save(dest, format="PNG")
            return str(dest)
        except Exception as e:
            logger.warning("生成二维码失败: %s", e)
            return None

    def _qr_poll_worker(self, seq: int, key: str) -> None:
        deadline = time.monotonic() + QR_POLL_MAX_SECONDS
        while self._qr_running and seq == self._qr_seq and time.monotonic() < deadline:
            time.sleep(QR_POLL_INTERVAL)
            if not (self._qr_running and seq == self._qr_seq):
                return
            try:
                result = wy_login_qr_check(key)
            except Exception as e:
                logger.debug("扫码状态查询异常: %s", e)
                continue
            if not isinstance(result, dict):
                continue
            code = result.get("code")
            cookie = result.get("cookie") or ""
            self._emitter.qrPoll.emit((seq, key, code, cookie))
            if code in (QR_SUCCESS, QR_EXPIRED) or (code == 200 and cookie):
                return
        self._emitter.qrPoll.emit((seq, key, -1, ""))

    @Slot(object)
    def _on_qr_poll(self, payload) -> None:
        seq, key, code, cookie = payload
        if seq != self._qr_seq or not self._qr_running:
            return
        if code == QR_SUCCESS or (code == 200 and cookie):
            self._qr_running = False
            self._apply_login_cookie(cookie)
        elif code == QR_EXPIRED:
            self._set_status("二维码已失效，正在刷新…")
            self._qr_running = False
            self._qr_image = ""
            self.qrChanged.emit()
            threading.Timer(0.8, self.startQrLogin).start()
        elif code == QR_SCANNED:
            self._set_status("扫描成功，请在手机上确认登录")
        elif code == QR_WAIT_SCAN:
            self._set_status("等待扫码…")
        elif code == -1:
            self._qr_running = False
            self._set_busy(False)
            self._set_status("二维码已超时，请重新获取")

    # ── 手机号 / 验证码 / Cookie ────────────────────────────

    @Slot(str, str, result=bool)
    def sendCaptcha(self, phone: str, countryCode: str = "86") -> bool:  # noqa: N802
        phone = (phone or "").strip()
        if not phone:
            self.errorOccurred.emit("请输入手机号")
            return False
        self._set_busy(True)
        self._set_status("正在发送验证码…")
        threading.Thread(
            target=self._captcha_worker, args=(phone, countryCode or "86"), daemon=True,
            name="wy-sms",
        ).start()
        return True

    def _captcha_worker(self, phone: str, ctcode: str) -> None:
        src = wy_source()
        resp: Dict[str, Any] = {}
        try:
            if src is not None:
                resp = src._eapi_post(  # noqa: SLF001
                    "/api/sms/captcha/sent", {"cellphone": phone, "ctcode": ctcode}
                ) or {}
        except Exception as e:
            logger.warning("发送验证码失败: %s", e)
        self._emitter.loginDone.emit(("captcha", resp))

    @Slot(str, str, str, bool)
    def loginWithPhone(
        self, phone: str, secret: str, countryCode: str = "86", usePassword: bool = False
    ) -> None:  # noqa: N802
        phone = (phone or "").strip()
        if not phone or not secret:
            self.errorOccurred.emit("请填写手机号与验证码/密码")
            return
        self._set_busy(True)
        self._set_status("正在登录…")
        threading.Thread(
            target=self._phone_login_worker,
            args=(phone, secret, countryCode or "86", bool(usePassword)),
            daemon=True,
            name="wy-phone-login",
        ).start()

    def _phone_login_worker(self, phone: str, secret: str, ctcode: str, use_password: bool) -> None:
        src = wy_source()
        resp: Dict[str, Any] = {}
        try:
            if src is not None:
                payload: Dict[str, Any] = {
                    "phone": phone,
                    "countrycode": ctcode,
                    "rememberLogin": True,
                }
                if use_password:
                    payload["password"] = secret
                else:
                    payload["captcha"] = secret
                resp = src._eapi_post("/api/login/cellphone", payload) or {}  # noqa: SLF001
        except Exception as e:
            logger.warning("手机号登录异常: %s", e)
            resp = {"code": -1, "message": str(e)}
        self._emitter.loginDone.emit(("phone", resp))

    @Slot(str)
    def loginWithCookie(self, cookie: str) -> None:  # noqa: N802
        cookie = (cookie or "").strip()
        if not cookie:
            self.errorOccurred.emit("请粘贴 Cookie")
            return
        self._set_busy(True)
        self._set_status("正在校验 Cookie…")
        self._apply_login_cookie(cookie)

    @Slot(object)
    def _on_login_done(self, payload) -> None:
        kind, resp = payload
        if kind == "captcha":
            code = (resp or {}).get("code")
            if code == 200:
                self._set_status("验证码已发送")
                self.message.emit("验证码已发送，请查看手机短信")
            else:
                self._set_busy(False)
                self._set_status("验证码发送失败")
                self.errorOccurred.emit(_describe_error(resp, "验证码发送失败"))
            return

        if kind == "phone":
            code = (resp or {}).get("code")
            if code == 200:
                cookie = wy_get_cookie_str()
                if wy_is_logged_in():
                    self._apply_login_cookie(cookie)
                else:
                    self._set_busy(False)
                    self._set_status("登录失败")
                    self.errorOccurred.emit("登录响应成功但未获取到登录凭据")
            else:
                self._set_busy(False)
                self._set_status("登录失败")
                self.errorOccurred.emit(_describe_error(resp, "登录失败"))

    # ── 登录成功后的统一处理 ────────────────────────────────

    def _apply_login_cookie(self, cookie: str) -> None:
        cookie = (cookie or "").replace(" HTTPOnly", "")
        if cookie:
            wy_apply_cookie(cookie)
        saved = wy_get_cookie_str() or cookie
        if not wy_is_logged_in():
            self._set_busy(False)
            self._set_status("登录失败")
            self.errorOccurred.emit("授权成功但未取到登录凭据，请重试")
            return

        self._logged_in = True
        self._set_status("已登录")
        self.loggedInChanged.emit()

        # 先保存凭据，再异步校验并补充昵称/头像
        self._persist_credentials(saved, {})
        threading.Thread(target=self._refresh_worker, daemon=True, name="wy-refresh").start()
        self.message.emit("登录成功")

    def _persist_credentials(self, cookies: str, profile: Dict[str, Any]) -> None:
        if not bool(self._config.get("account.save_credentials", True)):
            return
        if not cookies:
            return
        payload = {
            "provider": PROVIDER,
            "cookies": cookies,
            "user_id": int(profile.get("user_id") or self._user_id or 0),
            "nickname": profile.get("nickname") or self._nickname or "",
            "avatar_url": profile.get("avatar_url") or self._avatar or "",
            "vip_type": int(profile.get("vip_type") or self._vip_type or 0),
            "has_music_package": bool(
                profile.get("has_music_package", self._has_music_package)
            ),
            "has_black_vip": bool(profile.get("has_black_vip", self._has_black_vip)),
            "is_svip": bool(profile.get("is_svip", self._is_svip)),
            "red_vip_level": int(profile.get("red_vip_level") or self._red_vip_level or 0),
            "red_vip_annual_count": int(
                profile.get("red_vip_annual_count") or self._red_vip_annual_count or 0
            ),
            "obtained_at": int(time.time()),
            "expires_at": int(time.time()) + MUSIC_U_TTL_SECONDS,
            "app_version": APP_VERSION,
        }
        try:
            ok = vault.save(payload)
            if not ok:
                self.errorOccurred.emit("凭据加密保存失败，本次登录状态不会被记住")
        except VaultError as e:
            self.errorOccurred.emit(str(e))
        except Exception as e:
            logger.warning("保存凭据失败: %s", e)
            self.errorOccurred.emit("凭据保存失败，本次登录状态不会被记住")

    def _refresh_worker(self) -> None:
        profile = None
        try:
            profile = wy_fetch_profile()
        except Exception as e:
            logger.debug("拉取账号信息失败: %s", e)
        self._emitter.profileDone.emit(profile)

    @Slot(object)
    def _on_profile_done(self, profile) -> None:
        self._set_busy(False)
        if not profile:
            if self._logged_in:
                self._set_status("登录状态可能已失效")
                self.errorOccurred.emit("服务端校验未通过，请尝试重新登录")
            else:
                # 即使拿不到账号信息也试着同步歌单（会话可能是有效的）
                threading.Thread(
                    target=self._playlists_worker, daemon=True, name="wy-playlists"
                ).start()
            return
        self._nickname = str(profile.get("nickname") or "")
        self._avatar = str(profile.get("avatar_url") or "")
        self._user_id = int(profile.get("user_id") or 0)
        self._apply_vip_fields(profile)
        self._set_status("已登录")
        self.profileChanged.emit()
        # 用服务端返回的完整信息覆盖一次凭据
        self._persist_credentials(
            wy_get_cookie_str(),
            {
                "user_id": self._user_id,
                "nickname": self._nickname,
                "avatar_url": self._avatar,
                "vip_type": self._vip_type,
                "has_music_package": self._has_music_package,
                "has_black_vip": self._has_black_vip,
                "is_svip": self._is_svip,
                "red_vip_level": self._red_vip_level,
                "red_vip_annual_count": self._red_vip_annual_count,
            },
        )
        threading.Thread(target=self._playlists_worker, daemon=True, name="wy-playlists").start()

    def _playlists_worker(self) -> None:
        try:
            items = wy_get_user_playlists()
        except Exception as e:
            logger.warning("拉取网易云歌单失败: %s", e)
            items = None
        self._emitter.playlistsDone.emit(items if items is not None else [])

    @Slot()
    def syncPlaylists(self) -> None:  # noqa: N802
        """手动重新同步网易云歌单。"""
        if not self._logged_in:
            self.errorOccurred.emit("请先登录网易云账号")
            return
        self._set_busy(True)
        self._set_status("正在同步歌单…")
        threading.Thread(target=self._playlists_worker, daemon=True, name="wy-playlists").start()

    @Slot(object)
    def _on_playlists_done(self, items) -> None:
        self._remote_playlists = list(items or [])
        self.playlistsChanged.emit()

    # ── 登出 ────────────────────────────────────────────────

    @Slot()
    def logout(self) -> None:
        wy_clear_cookie()
        try:
            vault.delete()
        except Exception as e:
            logger.warning("删除凭据失败: %s", e)
        self._logged_in = False
        self._nickname = ""
        self._avatar = ""
        self._user_id = 0
        self._vip_type = 0
        self._has_music_package = False
        self._has_black_vip = False
        self._is_svip = False
        self._red_vip_level = 0
        self._red_vip_annual_count = 0
        self._remote_playlists = []
        self._qr_image = ""
        self._set_status("已退出登录")
        self._set_busy(False)
        self.loggedInChanged.emit()
        self.profileChanged.emit()
        self.playlistsChanged.emit()
        self.qrChanged.emit()
        self.message.emit("已退出登录，本地凭据已删除")

    @Slot()
    def refresh(self) -> None:
        if not self._logged_in:
            return
        self._set_busy(True)
        threading.Thread(target=self._refresh_worker, daemon=True, name="wy-refresh").start()

    # ── 内部工具 ────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        if text != self._status:
            self._status = text
            self.statusChanged.emit()

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busyChanged.emit()

def _describe_error(resp: Any, fallback: str) -> str:
    if not isinstance(resp, dict):
        return fallback
    code = resp.get("code")
    msg = str(resp.get("message") or resp.get("msg") or "").strip()
    if code == 502:
        return "网易已下线该登录方式，请改用扫码登录或短信验证码登录"
    if code == 503:
        return "验证码错误或已过期"
    if code == 501:
        return "账号或密码错误"
    if code == 400:
        return "请求被拒绝，请稍后重试"
    if msg:
        return f"{fallback}：{msg}"
    return f"{fallback}（错误码 {code}）" if code is not None else fallback
