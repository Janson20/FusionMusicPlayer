"""手机扫码登录的本地辅助：局域网地址、内存二维码与二维码渲染。"""

from __future__ import annotations

import io
import socket
import threading
from typing import List, Optional

from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider


class TransferError(RuntimeError):
    """可以直接显示给用户的传输错误。"""


def _private_scope(ip: str) -> Optional[int]:
    """返回私网地址的优先级；不是可用的局域网地址时返回 None。"""
    try:
        parts = [int(piece) for piece in str(ip).split(".")]
    except (TypeError, ValueError):
        return None
    if len(parts) != 4 or any(part < 0 or part > 255 for part in parts):
        return None
    a, b, _c, _d = parts
    if a == 127 or a == 0 or a >= 224:
        return None
    if a == 10:
        return 0
    if a == 172 and 16 <= b <= 31:
        return 0
    if a == 192 and b == 168:
        return 0
    if a == 169 and b == 254:
        return 2
    return None


def is_private_ipv4(ip: str) -> bool:
    return _private_scope(ip) is not None


def _default_route_ipv4() -> Optional[str]:
    """不真正发包地让系统选出默认出口地址。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        value = str(sock.getsockname()[0])
        return value if is_private_ipv4(value) else None
    except OSError:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def discover_lan_ipv4() -> List[str]:
    """列出可用的私网 IPv4，首项优先默认路由。

    Windows 上 gethostbyname_ex 有时会漏掉虚拟网卡，因此先拿 UDP 路由选出的
    地址，再补上主机名解析结果；电脑插网线 + 连 Wi-Fi 时会有多个候选。
    """
    candidates: List[str] = []
    default = _default_route_ipv4()
    if default:
        candidates.append(default)
    try:
        _name, _aliases, addresses = socket.gethostbyname_ex(socket.gethostname())
    except OSError:
        addresses = []
    for address in addresses:
        if is_private_ipv4(address):
            candidates.append(str(address))

    ordered: List[str] = []
    for address in candidates:
        if address not in ordered:
            ordered.append(address)
    ordered.sort(key=lambda item: _address_rank(item, default))
    return ordered


def _address_rank(ip: str, default: Optional[str]) -> int:
    """给手机扫码用的地址排序。

    用户环境里常见 VPN / WSL / Hyper-V 的 10.x、172.x、192.168.x.1，
    而真正给手机连的通常是 192.168.x.x 的物理网卡。这里明确把 192.168
    放到最前，再在组内优先默认路由和常见主机地址（非 .1），避免电脑端
    一上来就选了虚拟网卡。
    """
    parts = str(ip).split(".")
    if len(parts) != 4:
        return 99
    try:
        a, b = int(parts[0]), int(parts[1])
    except ValueError:
        return 99
    host_last = parts[3]
    if a == 192 and b == 168:
        if host_last == "1":
            return 2 if ip == default else 3
        return 0 if ip == default else 1
    if a == 10:
        return 10 if ip == default else 11
    if a == 172 and 16 <= b <= 31:
        return 20 if ip == default else 21
    if a == 169 and b == 254:
        return 30 if ip == default else 31
    return 99


class TransferQrProvider(QQuickImageProvider):
    """在内存里保存二维码，避免带临时密钥的图片落到磁盘缓存。"""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.Image)
        self._lock = threading.Lock()
        self._image = QImage()
        self._generation = 0

    def set_png(self, png: bytes) -> str:
        image = QImage.fromData(png, "PNG")
        if image.isNull():
            raise TransferError("二维码图像生成失败")
        with self._lock:
            self._generation += 1
            self._image = image
            generation = self._generation
        return f"image://login-transfer/{generation}"

    def clear(self) -> None:
        with self._lock:
            self._generation += 1
            self._image = QImage()

    def requestImage(self, image_id, size, requested_size):  # noqa: N802
        with self._lock:
            image = self._image
        if not image.isNull() and size is not None:
            try:
                size.setWidth(image.width())
                size.setHeight(image.height())
            except Exception:
                pass
        return image


def render_qr_png(data: str, size: int = 320) -> bytes:
    """本地渲染二维码为 PNG 字节；不写磁盘。"""
    try:
        import qrcode
        from PIL import Image
    except Exception as exc:  # pragma: no cover - 依赖缺失时走这里
        raise TransferError("缺少二维码依赖 qrcode / Pillow，无法生成手机扫码登录码") from exc
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=3,
        )
        qr.add_data(data)
        qr.make(fit=True)
        image = qr.make_image(fill_color="#14121F", back_color="white").convert("RGB")
        resample = getattr(getattr(Image, "Resampling", Image), "NEAREST", Image.NEAREST)
        image = image.resize((size, size), resample)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except TransferError:
        raise
    except Exception as exc:
        raise TransferError("二维码生成失败") from exc
