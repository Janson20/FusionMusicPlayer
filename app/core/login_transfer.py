"""桌面 → 手机的一次性网易云登录凭据传输。

设计要点
--------
* 二维码只带**一次性取件地址、token 与临时 AES 密钥**，不带 Cookie 明文；
* 密文由桌面在局域网里临时提供的 HTTP 服务返回，服务端只认 token；
* AES-256-GCM 的 AAD 绑定 token 与过期时间，手机端必须持有二维码里的密钥才能解开；
* token 成功使用一次即失效，二维码默认 180 秒过期；
* 服务只绑定当前局域网 IPv4，不监听 0.0.0.0，不记录密钥或凭据、不落盘。

二维码渲染、内存图像与网卡选择在 login_qr 里；本模块只做协议、加密与临时服务。
"""

from __future__ import annotations

import base64
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .login_qr import TransferError, is_private_ipv4

logger = logging.getLogger(__name__)

TRANSFER_SCHEME = "fusionmusic"
TRANSFER_HOST = "login-transfer"
TRANSFER_VERSION = 1
TRANSFER_PATH = "/v1/credential"
TRANSFER_TTL_SECONDS = 180
AAD_PREFIX = "FusionMusicPlayer/login-transfer/v1"
MAX_INVALID_REQUESTS = 8


@dataclass(frozen=True)
class TransferTicket:
    uri: str
    host: str
    port: int
    expires_at: int


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _aad(token: str, expires_at: int) -> bytes:
    return f"{AAD_PREFIX}|{token}|{int(expires_at)}".encode("utf-8")


class _TransferHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FusionMusicPlayer"
    sys_version = ""

    def do_POST(self) -> None:  # noqa: N802
        session = getattr(self.server, "transfer_session", None)
        if session is None:
            self._send(503, {"ok": False, "error": "unavailable"})
            return
        if self.path != TRANSFER_PATH:
            self._send(404, {"ok": False, "error": "not_found"})
            return
        raw_length = str(self.headers.get("Content-Length", "0") or "0").strip()
        try:
            length = int(raw_length)
        except ValueError:
            self._send(400, {"ok": False, "error": "bad_request"})
            return
        if length < 0 or length > 1024:
            self._send(413, {"ok": False, "error": "too_large"})
            return
        if length:
            self.rfile.read(length)

        auth = str(self.headers.get("Authorization", "") or "")
        if not auth.startswith("Bearer "):
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        token = auth[7:].strip()
        status, body, delivered = session.claim(token, self.client_address[0])
        sent = self._send(status, body)
        if delivered:
            # 客户端可能因为网络抖动没收到，但 token 已经消耗；提示用户重新生成即可。
            session.notify_sent()
            logger.info("手机登录凭据已取件（http_sent=%s）", sent)

    def do_GET(self) -> None:  # noqa: N802
        self._send(405, {"ok": False, "error": "method_not_allowed"})

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send(405, {"ok": False, "error": "method_not_allowed"})

    def _send(self, status: int, body: Dict[str, Any]) -> bool:
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(int(status))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()
            return True
        except OSError:
            return False
        finally:
            self.close_connection = True

    def log_message(self, fmt: str, *args) -> None:
        # BaseHTTPRequestHandler 默认写到 stderr；这里只保留方法/路径，不带请求头。
        logger.debug("登录传输 HTTP: " + fmt, *args)


class _TransferServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def server_bind(self) -> None:
        """跳过 HTTPServer.server_bind 里的 socket.getfqdn。

        Windows 上方向解析主机名可能卡几秒到几十秒；主线程曾因此显示
        「未响应」，工作线程也会让二维码迟迟不出来。server_name 只是
        HTTP 日志用，这里直接用 IP，不需要 FQDN。
        """
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = int(port)


class LoginTransferSession:
    """一次二维码对应的临时服务；所有敏感材料只保存在进程内存。"""

    def __init__(
        self,
        credential: Dict[str, Any],
        host: str,
        *,
        ttl: int = TRANSFER_TTL_SECONDS,
        on_event: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        if not is_private_ipv4(host):
            raise TransferError("当前没有可用于手机连接的局域网 IPv4 地址")
        if not isinstance(credential, dict) or not credential.get("cookies"):
            raise TransferError("当前没有可传输的登录凭据")
        self._credential = dict(credential)
        self._host = str(host)
        self._ttl = max(30, int(ttl))
        self._on_event = on_event
        self._lock = threading.Lock()
        self._token = ""
        self._key: Optional[bytes] = None
        self._nonce = b""
        self._ciphertext = b""
        self._response: Dict[str, Any] = {}
        self._expires_at = 0
        self._port = 0
        self._httpd: Optional[_TransferServer] = None
        self._thread: Optional[threading.Thread] = None
        self._timer: Optional[threading.Timer] = None
        self._stop_thread: Optional[threading.Thread] = None
        self._used = False
        self._invalid_requests = 0
        self._stopped = False
        self._sent_notified = False

    @property
    def expires_at(self) -> int:
        return self._expires_at

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> TransferTicket:
        if self._httpd is not None:
            raise TransferError("登录传输已在运行")
        token = _b64u_encode(secrets.token_bytes(32))
        key = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)
        expires_at = int(time.time()) + self._ttl
        inner = {
            "schema": "fusion-login-transfer",
            "version": TRANSFER_VERSION,
            "provider": "netease",
            "created_at": int(time.time()),
            "credential": dict(self._credential),
        }
        plaintext = json.dumps(inner, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        try:
            ciphertext = AESGCM(key).encrypt(nonce, plaintext, _aad(token, expires_at))
        except Exception as exc:
            raise TransferError("登录凭据加密失败") from exc

        server: Optional[_TransferServer] = None
        try:
            server = _TransferServer((self._host, 0), _TransferHandler)
            server.transfer_session = self  # type: ignore[attr-defined]
            port = int(server.server_address[1])
        except OSError as exc:
            if server is not None:
                try:
                    server.server_close()
                except OSError:
                    pass
            raise TransferError(f"无法在 {self._host} 启动临时服务，请检查防火墙或端口占用") from exc

        self._token = token
        self._key = key
        self._nonce = nonce
        self._ciphertext = ciphertext
        self._expires_at = expires_at
        self._port = port
        self._response = {
            "ok": True,
            "v": TRANSFER_VERSION,
            "alg": "AES-256-GCM",
            "nonce": _b64u_encode(nonce),
            "data": _b64u_encode(ciphertext),
            "expires_at": expires_at,
        }
        self._httpd = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.1},
            daemon=True,
            name="login-transfer-http",
        )
        self._thread.start()
        self._timer = threading.Timer(self._ttl, self._on_timeout)
        self._timer.daemon = True
        self._timer.start()

        query = urlencode(
            {
                "v": TRANSFER_VERSION,
                "h": self._host,
                "p": port,
                "t": token,
                "k": _b64u_encode(key),
                "e": expires_at,
            }
        )
        return TransferTicket(
            uri=f"{TRANSFER_SCHEME}://{TRANSFER_HOST}?{query}",
            host=self._host,
            port=port,
            expires_at=expires_at,
        )

    def claim(self, token: str, client_ip: str) -> Tuple[int, Dict[str, Any], bool]:
        now = int(time.time())
        expired = False
        invalid = False
        with self._lock:
            if self._stopped:
                return 410, {"ok": False, "error": "expired"}, False
            if now >= self._expires_at:
                expired = True
            elif self._used:
                return 409, {"ok": False, "error": "already_used"}, False
            elif not hmac.compare_digest(str(token or ""), self._token):
                self._invalid_requests += 1
                invalid = self._invalid_requests >= MAX_INVALID_REQUESTS
            else:
                self._used = True
                logger.info("登录凭据被局域网设备取件: %s", str(client_ip or "?"))
                return 200, dict(self._response), True
        if expired:
            self._defer_stop("expired")
            return 410, {"ok": False, "error": "expired"}, False
        if invalid:
            self._defer_stop("failed")
            return 401, {"ok": False, "error": "unauthorized"}, False
        return 401, {"ok": False, "error": "unauthorized"}, False

    def notify_sent(self) -> None:
        with self._lock:
            if self._sent_notified:
                return
            self._sent_notified = True
        self._emit("sent", "凭据已发送到手机")
        # 给 HTTP 响应留一点写完的时间，再从另一个线程关闭监听。
        self._defer_stop("sent")

    def stop(self, reason: str = "cancelled") -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            timer = self._timer
            httpd = self._httpd
            self._timer = None
            self._httpd = None
            self._key = None
            self._nonce = b""
            self._ciphertext = b""
            self._response = {}
            self._credential = {}
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass
        if httpd is not None and self._stop_thread is None:
            self._stop_thread = threading.Thread(
                target=self._close_server,
                args=(httpd,),
                daemon=True,
                name="login-transfer-stop",
            )
            self._stop_thread.start()
        if reason != "sent":
            self._emit(reason, self._reason_text(reason))

    def _close_server(self, httpd: _TransferServer) -> None:
        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass

    def _defer_stop(self, reason: str, delay: float = 0.4) -> None:
        """延迟关闭监听，避免把正在写的 HTTP 响应一起掐断。"""
        timer = threading.Timer(delay, lambda: self.stop(reason))
        timer.daemon = True
        timer.start()

    def _on_timeout(self) -> None:
        self.stop("expired")

    @staticmethod
    def _reason_text(reason: str) -> str:
        return {
            "expired": "二维码已过期",
            "cancelled": "已取消手机扫码登录",
            "failed": "登录传输失败，请重新生成二维码",
        }.get(reason, "登录传输已停止")

    def _emit(self, event: str, detail: str) -> None:
        callback = self._on_event
        if callback is None:
            return
        try:
            callback(event, detail)
        except Exception as exc:  # pragma: no cover - 回调不应影响服务收尾
            logger.debug("登录传输回调异常: %s", exc)
