#!/usr/bin/env python3
"""生成启动画面底图（``assets/splash-dark.dat`` / ``assets/splash-light.dat``）。

为什么要有这个脚本
------------------
启动画面必须在 **Qt 起来之前** 显示，所以运行时不能用 Qt 解码图片，也不该为了
一张图把 Pillow 变成运行时依赖。折中方案：底图在**开发期**用 Pillow 画好，
存成自描述的二进制（头部 + zlib 压缩的预乘 BGRA），运行时只用 ``zlib`` 解压、
``CreateDIBSection`` 上屏。于是：

* 运行时零新增依赖（``zlib`` 是标准库）；
* 资源完全由本脚本生成，来源可追溯，仓库里没有任何"来源不明的二进制"；
* 动态内容（状态文字、进度条）不烘进图里 —— 那是 GDI 按屏幕 DPI 现画的，
  100%/150%/200% 缩放下都清晰。

用法::

    python tools/make_splash.py            # 生成到 assets/
    python tools/make_splash.py --check    # 校验仓库里的文件是否与脚本一致
    python tools/make_splash.py --preview D:\\tmp  # 顺便导出 PNG 预览

文件格式（小端）::

    0   4s  magic "FMPS"
    4   H   version = 1
    6   H   flags = 0
    8   I   width, height        逻辑尺寸（布局字段的单位）
    16  I   art_width, art_height 底图像素尺寸（= 逻辑尺寸 × ART_SCALE）
    24  I   stride, raw_len, zlen
    36  I   title_x, title_y, title_w, title_h
    52  I   status_x, status_y, status_w, status_h
    68  I   bar_x, bar_y, bar_w, bar_h
    84  I   title_color, status_color   COLORREF(0x00BBGGRR)
    92  I   title_px, status_px         字号（逻辑像素）
    100 I   reserved
    104 载荷：zlib 压缩的预乘 BGRA，逐行自上而下
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICON = ASSETS / "icon.png"

MAGIC = b"FMPS"
VERSION = 1
HEADER_SIZE = 104  # 4+2+2 + 24×4 字节字段
ART_SCALE = 2  # 底图按 2 倍逻辑尺寸绘制：200% 缩放 1:1，100%/150% 降采样后依然干净

W, H = 420, 260
RADIUS = 16

LAYOUT = {
    "icon": (166, 42, 88, 88),
    "title": (24, 142, 372, 32),
    "status": (24, 184, 372, 18),
    "bar": (26, 220, 368, 3),
}
TITLE_PX = 21
STATUS_PX = 12

THEMES = {
    "dark": {
        "card": (31, 31, 35, 255),
        "border": (51, 51, 58, 255),
        "track": (53, 53, 60, 255),
        "title": (242, 242, 246),
        "status": (160, 160, 170),
    },
    "light": {
        "card": (251, 251, 252, 255),
        "border": (226, 226, 232, 255),
        "track": (231, 231, 236, 255),
        "title": (26, 26, 30),
        "status": (108, 108, 118),
    },
}


def _colorref(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (b << 16) | (g << 8) | r


def _scale_box(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x, y, w, h = box
    s = ART_SCALE
    return x * s, y * s, w * s, h * s


def render(theme: str) -> Image.Image:
    """画一张底图：卡片 + 图标 + 进度条轨道（文字留给运行时 GDI）。"""
    palette = THEMES[theme]
    s = ART_SCALE
    canvas = Image.new("RGBA", (W * s, H * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    draw.rounded_rectangle(
        (0, 0, W * s - 1, H * s - 1),
        radius=RADIUS * s,
        fill=palette["card"],
        outline=palette["border"],
        width=s,
    )

    icon = Image.open(ICON).convert("RGBA")
    ix, iy, iw, ih = _scale_box(LAYOUT["icon"])
    canvas.alpha_composite(icon.resize((iw, ih), Image.LANCZOS), (ix, iy))

    bx, by, bw, bh = _scale_box(LAYOUT["bar"])
    draw.rounded_rectangle((bx, by, bx + bw - 1, by + bh - 1), radius=bh // 2, fill=palette["track"])
    return canvas


def encode(image: Image.Image, theme: str) -> bytes:
    """RGBA 底图 → 带头部的预乘 BGRA 数据。

    ``UpdateLayeredWindow`` 要求 **预乘 alpha**（否则半透明像素会发白）。
    """
    palette = THEMES[theme]
    r, g, b, a = image.split()
    premul = Image.merge(
        "RGBA",
        (ImageChops.multiply(r, a), ImageChops.multiply(g, a), ImageChops.multiply(b, a), a),
    )
    raw = premul.tobytes("raw", "BGRA")
    payload = zlib.compress(raw, 9)
    stride = image.width * 4
    fields = (
        W,
        H,
        image.width,
        image.height,
        stride,
        len(raw),
        len(payload),
        *LAYOUT["title"],
        *LAYOUT["status"],
        *LAYOUT["bar"],
        _colorref(palette["title"]),
        _colorref(palette["status"]),
        TITLE_PX,
        STATUS_PX,
        0,
    )
    header = struct.pack("<4sHH", MAGIC, VERSION, 0) + struct.pack(f"<{len(fields)}I", *fields)
    assert len(header) == HEADER_SIZE, len(header)
    return header + payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="生成启动画面底图")
    parser.add_argument("--check", action="store_true", help="只校验，不写文件")
    parser.add_argument("--preview", metavar="DIR", help="额外导出 PNG 预览到该目录")
    args = parser.parse_args(argv[1:])

    if not ICON.exists():
        print(f"找不到图标：{ICON}", file=sys.stderr)
        return 2

    drift = 0
    for theme in THEMES:
        target = ASSETS / f"splash-{theme}.dat"
        data = encode(render(theme), theme)
        if args.check:
            current = target.read_bytes() if target.exists() else b""
            if current == data:
                print(f"{target.name}: OK（{len(data) // 1024} KB）")
            else:
                drift += 1
                print(f"{target.name}: 与脚本不一致（{len(current)} → {len(data)} 字节）")
        else:
            target.write_bytes(data)
            print(f"已写入 {target}（{len(data) // 1024} KB）")
        if args.preview:
            out = Path(args.preview) / f"splash-{theme}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            render(theme).resize((W, H), Image.LANCZOS).save(out)
            print(f"预览 {out}")
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
