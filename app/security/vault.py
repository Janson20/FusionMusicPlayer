"""凭据加密存储。

设计目标（相对 FMCL ``secure_storage.py`` 的改进）
------------------------------------------------
1. **带版本的自描述信封**：文件头写明 ``format_version`` / ``cipher`` / ``kdf`` /
   ``iterations`` / ``salt`` / ``nonce``，换算法或换参数时仍可读旧文件。
2. **认证加密**：AES-256-GCM，密文被篡改会直接解密失败，不会像 Fernet + base64
   回退那样把损坏数据当明文返回。
3. **绝不静默重建密钥**：密钥文件存在但损坏时抛 :class:`VaultError` 并保留原文件，
   不会覆盖导致旧凭据永久不可解。
4. **原子落盘**：先写临时文件再 ``os.replace``，避免中途崩溃留下半截文件。
5. **密钥与密文强制分离**，两者都在程序目录下，保证绿色便携。

密钥装载优先级
--------------
1. 环境变量 ``FUSION_MUSIC_MASTER_PASSWORD`` → PBKDF2-HMAC-SHA256(600k) 派生（真加密，
   换机可用，但忘记主密码即丢失凭据）。
2. ``data/keys/master.key``：32 字节随机主密钥。Windows 上用 **DPAPI（用户作用域）**
   包裹，因此该文件被拷到别的机器/别的 Windows 用户下无法解开；其它平台直接存原始
   字节并收紧为 0600。

安全边界（务必知悉）
--------------------
密钥文件与密文同处一个可拷贝目录中，因此本方案的定位是「防止凭据以明文形式暴露」
（配置文件被查看、同步、误发、日志泄漏），**不是**对能读取该目录的本地攻击者的防护。
需要更强保护时请启用主密码模式。
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import secrets
import stat
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

from .. import paths

logger = logging.getLogger(__name__)

FORMAT_VERSION = 1
CIPHER = "aes-256-gcm"
KDF_HKDF = "hkdf-sha256"
KDF_PBKDF2 = "pbkdf2-sha256"
PBKDF2_ITERATIONS = 600_000
KEY_BYTES = 32
NONCE_BYTES = 12
SALT_BYTES = 32
HKDF_INFO = b"FusionMusicPlayer/credentials/v1"
MASTER_PASSWORD_ENV = "FUSION_MUSIC_MASTER_PASSWORD"


class VaultError(RuntimeError):
    """凭据加解密或密钥装载失败。"""


# ──────────────────────────────────────────────────────────────
# DPAPI（仅 Windows）
# ──────────────────────────────────────────────────────────────


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_available() -> bool:
    return sys.platform == "win32"


def _dpapi_protect(data: bytes) -> Optional[bytes]:
    """用当前 Windows 用户的 DPAPI 凭据加密数据。"""
    if not _dpapi_available():
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        blob_in = _DataBlob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
        blob_out = _DataBlob()
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
    except Exception as e:  # pragma: no cover - 平台相关
        logger.debug("DPAPI 加密失败: %s", e)
        return None


def _dpapi_unprotect(data: bytes) -> Optional[bytes]:
    """解开 DPAPI 保护的数据。"""
    if not _dpapi_available():
        return None
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        blob_in = _DataBlob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
        blob_out = _DataBlob()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        )
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
    except Exception as e:  # pragma: no cover - 平台相关
        logger.debug("DPAPI 解密失败: %s", e)
        return None


# ──────────────────────────────────────────────────────────────
# 文件权限
# ──────────────────────────────────────────────────────────────


def _restrict_permissions(path: Path) -> None:
    """把文件权限收紧到「仅当前用户」。

    Windows 上用 ``/inheritance:r`` 去掉继承来的 ACE（这样同一台机器上的其它
    用户读不到），再只授予当前用户权限。**必须给完全控制（F）而不是只读+写**：
    ``(R,W)`` 不含删除权限，会导致用户无法删除自己的数据目录。
    """
    try:
        if os.name == "posix":
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            return
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        if not user:
            return
        proc = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode != 0:
            logger.debug(
                "收紧文件权限失败（非致命）: %s -> %s",
                path,
                (proc.stderr or proc.stdout or b"").decode("utf-8", "ignore").strip(),
            )
    except Exception as e:
        logger.debug("收紧文件权限异常（非致命）: %s - %s", path, e)


def _atomic_write(path: Path, data: bytes) -> None:
    """原子写入：临时文件 + os.replace。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _restrict_permissions(path)


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


# ──────────────────────────────────────────────────────────────
# 主密钥装载
# ──────────────────────────────────────────────────────────────


class _MasterKey:
    """已装载的主密钥及其来源描述。"""

    __slots__ = ("raw", "source", "fingerprint")

    def __init__(self, raw: bytes, source: str):
        self.raw = raw
        self.source = source
        import hashlib

        self.fingerprint = hashlib.sha256(raw).hexdigest()[:16]


def _load_or_create_master_key() -> _MasterKey:
    """装载主密钥；不存在则创建。绝不覆盖已存在但损坏的密钥文件。"""
    password = os.environ.get(MASTER_PASSWORD_ENV)
    if password:
        salt = _load_or_create_salt()
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_BYTES,
            salt=salt,
            iterations=PBKDF2_ITERATIONS,
        )
        return _MasterKey(kdf.derive(password.encode("utf-8")), "password")

    key_path = paths.key_file()
    if key_path.exists():
        raw = key_path.read_bytes()
        if raw:
            # 1) 先尝试 DPAPI 包裹格式
            if raw[:4] == b"DPA1":
                unwrapped = _dpapi_unprotect(raw[4:])
                if unwrapped is None:
                    raise VaultError(
                        "密钥文件由另一个 Windows 用户或另一台机器保护，无法解开。\n"
                        f"路径: {key_path}\n如需继续，请删除该文件后重新登录（旧凭据将失效）。"
                    )
                if len(unwrapped) == KEY_BYTES:
                    return _MasterKey(unwrapped, "dpapi")
            # 2) 裸密钥（非 Windows 或 DPAPI 不可用时的回退）
            if len(raw) == KEY_BYTES:
                return _MasterKey(raw, "keyfile")
        raise VaultError(
            f"密钥文件已损坏或格式无法识别: {key_path}\n"
            "为避免旧凭据永久不可解，程序不会自动覆盖它。"
            "请手动移走该文件后重新启动并重新登录。"
        )

    raw = secrets.token_bytes(KEY_BYTES)
    blob = _dpapi_protect(raw)
    if blob is not None:
        _atomic_write(key_path, b"DPA1" + blob)
        return _MasterKey(raw, "dpapi")
    _atomic_write(key_path, raw)
    return _MasterKey(raw, "keyfile")


def _load_or_create_salt() -> bytes:
    """主密码模式下用于 PBKDF2 的盐（存放在密钥目录，可随程序目录迁移）。"""
    salt_path = paths.key_file().parent / "master.salt"
    if salt_path.exists():
        data = salt_path.read_bytes()
        if len(data) >= 16:
            return data
        raise VaultError(f"盐文件已损坏: {salt_path}")
    salt = secrets.token_bytes(SALT_BYTES)
    _atomic_write(salt_path, salt)
    return salt


# ──────────────────────────────────────────────────────────────
# Vault
# ──────────────────────────────────────────────────────────────


class CredentialVault:
    """加密凭据仓库，默认落盘到 ``<程序目录>/data/credentials.enc``。"""

    def __init__(self, path: Optional[Path] = None):
        self._path = Path(path) if path else paths.credentials_file()
        self._master: Optional[_MasterKey] = None
        self._cache: Optional[Dict[str, Any]] = None
        self._loaded = False

    # ── 内部 ────────────────────────────────────────────────

    def _master_key(self) -> _MasterKey:
        if self._master is None:
            self._master = _load_or_create_master_key()
        return self._master

    def _derive_data_key(self, salt: bytes, kdf_name: str, iterations: int) -> bytes:
        master = self._master_key()
        if kdf_name == KDF_PBKDF2:
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(), length=KEY_BYTES, salt=salt, iterations=iterations
            )
            return kdf.derive(master.raw)
        hkdf = HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=salt, info=HKDF_INFO)
        return hkdf.derive(master.raw)

    # ── 公开 API ────────────────────────────────────────────

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, payload: Dict[str, Any]) -> bool:
        """加密并原子写入凭据。加密失败时**不落盘**，返回 False。"""
        try:
            salt = secrets.token_bytes(SALT_BYTES)
            kdf_name = KDF_PBKDF2 if os.environ.get(MASTER_PASSWORD_ENV) else KDF_HKDF
            iterations = PBKDF2_ITERATIONS if kdf_name == KDF_PBKDF2 else 0
            data_key = self._derive_data_key(salt, kdf_name, iterations)
            nonce = secrets.token_bytes(NONCE_BYTES)

            plaintext = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            # 信封头部作为 AAD 参与认证，防止降级篡改
            envelope_meta = {
                "format_version": FORMAT_VERSION,
                "cipher": CIPHER,
                "kdf": kdf_name,
                "iterations": iterations,
                "salt": _b64e(salt),
                "nonce": _b64e(nonce),
                "key_source": self._master_key().source,
                "saved_at": int(time.time()),
            }
            aad = json.dumps(envelope_meta, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ciphertext = AESGCM(data_key).encrypt(nonce, plaintext, aad)

            envelope = dict(envelope_meta)
            envelope["payload"] = _b64e(ciphertext)
            _atomic_write(self._path, json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8"))
            self._cache = dict(payload)
            self._loaded = True
            logger.info("凭据已加密保存: %s (key_source=%s)", self._path, envelope_meta["key_source"])
            return True
        except VaultError:
            raise
        except Exception as e:
            logger.error("凭据加密保存失败，已放弃写入以避免明文落盘: %s", e)
            return False

    def load(self, *, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """解密读取凭据。文件不存在或解密失败返回 None（绝不返回密文）。"""
        if use_cache and self._loaded:
            return dict(self._cache) if self._cache else None
        if not self._path.exists():
            self._loaded = True
            self._cache = None
            return None
        try:
            envelope = json.loads(self._path.read_text(encoding="utf-8"))
            version = int(envelope.get("format_version", 0))
            if version != FORMAT_VERSION:
                raise VaultError(f"不支持的凭据文件版本: {version}")
            if envelope.get("cipher") != CIPHER:
                raise VaultError(f"不支持的加密算法: {envelope.get('cipher')}")

            salt = _b64d(envelope["salt"])
            nonce = _b64d(envelope["nonce"])
            iterations = int(envelope.get("iterations") or 0)
            data_key = self._derive_data_key(salt, envelope.get("kdf", KDF_HKDF), iterations)

            meta = {
                k: envelope[k]
                for k in (
                    "format_version",
                    "cipher",
                    "kdf",
                    "iterations",
                    "salt",
                    "nonce",
                    "key_source",
                    "saved_at",
                )
                if k in envelope
            }
            aad = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")
            plaintext = AESGCM(data_key).decrypt(nonce, _b64d(envelope["payload"]), aad)
            payload = json.loads(plaintext.decode("utf-8"))
            self._cache = payload
            self._loaded = True
            return dict(payload)
        except VaultError:
            raise
        except Exception as e:
            logger.warning("凭据解密失败（文件可能损坏或密钥不匹配）: %s", e)
            self._loaded = True
            self._cache = None
            return None

    def delete(self) -> None:
        """删除凭据文件（保留主密钥，便于以后换账号复用）。"""
        self._cache = None
        self._loaded = True
        try:
            if self._path.exists():
                self._path.unlink()
                logger.info("凭据文件已删除: %s", self._path)
        except OSError as e:
            logger.warning("删除凭据文件失败: %s", e)

    def key_source(self) -> str:
        """密钥来源描述。未真正需要密钥时不创建它，保持数据目录干净。"""
        if os.environ.get(MASTER_PASSWORD_ENV):
            return "password"
        if not paths.key_file().exists():
            return "未生成"
        try:
            return self._master_key().source
        except VaultError:
            return "不可用"

    def key_fingerprint(self) -> str:
        if not paths.key_file().exists() and not os.environ.get(MASTER_PASSWORD_ENV):
            return "-"
        try:
            return self._master_key().fingerprint
        except VaultError:
            return "-"

    def describe(self) -> Dict[str, Any]:
        return {
            "path": str(self._path),
            "exists": self.exists(),
            "key_source": self.key_source(),
            "key_fingerprint": self.key_fingerprint(),
            "cipher": CIPHER,
            "format_version": FORMAT_VERSION,
        }


vault = CredentialVault()
