#!/usr/bin/env python3
"""账号诊断：读取已保存的加密凭据，打印网易云返回的会员字段。

用途：VIP / SVIP 识别不对时，用它看服务端到底返回了什么。
**不会打印 Cookie 本身**，只打印字段名与值。

用法::

    python tools/account_probe.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

from app.security import vault  # noqa: E402
from app.sources import SOURCE_NAMES, get_source  # noqa: E402

SENSITIVE = {"cookie", "cookies", "music_u", "csrf", "__csrf", "token", "password"}


def redact(obj, depth: int = 0):
    """递归脱敏：只保留结构，凭据类字段一律遮掉。"""
    if depth > 4:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE:
                out[k] = "***"
            else:
                out[k] = redact(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [redact(x, depth + 1) for x in obj[:3]]
    return obj


def main() -> int:
    print("=== 1. 已保存的凭据 ===")
    try:
        payload = vault.load()
    except Exception as e:
        print(f"读取凭据失败：{e}")
        return 1
    if not payload:
        print("没有找到已保存的凭据（data/credentials.enc）")
        return 1
    print(json.dumps(redact(payload), ensure_ascii=False, indent=2))

    cookies = payload.get("cookies") or ""
    print(f"\nCookie 长度: {len(cookies)} 字符")
    print(f"包含 MUSIC_U: {'MUSIC_U=' in cookies}")

    print("\n=== 2. 应用到会话 ===")
    src = get_source("wy")
    if src is None:
        print("网易云音源加载失败")
        return 1
    src.apply_cookie_str(cookies)
    print("已登录:", src.is_logged_in())

    print("\n=== 3. /api/nuser/account/get 原始响应（已脱敏）===")
    try:
        resp = src._eapi_post("/api/nuser/account/get", {})  # noqa: SLF001
    except Exception as e:
        print(f"请求失败：{e}")
        return 1
    print(json.dumps(redact(resp), ensure_ascii=False, indent=2))

    account = resp.get("account") or {}
    profile = resp.get("profile") or {}
    rights = profile.get("vipRights") or {}

    print("\n=== 4. 会员字段对照 ===")
    print(f"  account.vipType            : {account.get('vipType')!r}")
    print(f"  profile.vipType            : {profile.get('vipType')!r}   <- 上游只读这个")
    print(f"  account.baoyueVersion      : {account.get('baoyueVersion')!r}")
    print(f"  profile.vipRights.redVipLevel     : {rights.get('redVipLevel')!r}")
    print(f"  profile.vipRights.redVipAnnualCount: {rights.get('redVipAnnualCount')!r}")
    print(f"  profile.vipRights.associator      : {bool(rights.get('associator'))}")
    print(f"  profile.vipRights.musicPackage    : {bool(rights.get('musicPackage'))}")
    print(f"  profile.vipRights.redplus         : {bool(rights.get('redplus'))}")

    print("\n=== 5. 修正后的解析结果 ===")
    print(json.dumps(src.fetch_login_profile(), ensure_ascii=False, indent=2))

    print("\n=== 6. 用户歌单 ===")
    playlists = src.get_user_playlists()
    if playlists is None:
        print("拉取失败（返回 None）")
    else:
        print(f"共 {len(playlists)} 个：")
        for pl in playlists[:15]:
            print(f"  {pl['id']:>12}  {pl['name']}  ({pl['track_count']} 首)")
        if len(playlists) > 15:
            print(f"  … 另有 {len(playlists) - 15} 个")

    print(f"\n音源类: {type(src).__module__}.{type(src).__name__}"
          f"  ({SOURCE_NAMES.get('wy', '')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
