"""探测网易云的**搜索联想**接口。

联想词有两条路子：``/api/search/suggest/web``（老 weapi，本机常被风控拦）
与 ``/api/search/suggest/keyword``（eapi，猜你想搜）。这里把两种通道、两种
URL 前缀都试一遍，看哪个真出数据、返回结构是什么。

用法::

    python tools/probe_search_suggest.py [关键词] [输出文件]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.lazy import requests  # noqa: E402
from app.sources.utils import wy_eapi, wy_weapi  # noqa: E402
from app.sources.wy import WY_API_BASE, WY_EAPI_BASE  # noqa: E402

CASES = [
    ("eapi /api/search/suggest/keyword", "eapi", f"{WY_EAPI_BASE}/api/search/suggest/keyword",
     "/api/search/suggest/keyword", {"s": "{kw}"}),
    ("eapi /search/suggest/keyword", "eapi", f"{WY_EAPI_BASE}/search/suggest/keyword",
     "/api/search/suggest/keyword", {"s": "{kw}"}),
    ("eapi /api/search/suggest/web", "eapi", f"{WY_EAPI_BASE}/api/search/suggest/web",
     "/api/search/suggest/web", {"s": "{kw}", "limit": 8}),
    ("weapi /api/search/suggest/web", "weapi", f"{WY_API_BASE}/search/suggest/web",
     "/api/search/suggest/web", {"s": "{kw}", "limit": 8}),
]


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "周杰"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("search_suggest_probe.txt")
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://music.163.com/",
    })

    out: list[str] = [f"关键词: {keyword}", ""]
    for label, kind, url, path, data in CASES:
        out.append("=" * 72)
        out.append(label)
        payload = {k: (v.replace("{kw}", keyword) if isinstance(v, str) else v)
                   for k, v in data.items()}
        try:
            if kind == "eapi":
                resp = session.post(url, data=wy_eapi(path, payload), timeout=15)
            else:
                resp = session.post(url, data=wy_weapi(payload), timeout=15)
            body = resp.json()
        except Exception as e:
            out.append(f"  失败: {type(e).__name__}: {e}")
            continue
        if not isinstance(body, dict):
            out.append(f"  非 JSON 对象: {type(body).__name__}")
            continue
        out.append(f"  code={body.get('code')} 顶层键={sorted(body.keys())}")
        result = body.get("result")
        if isinstance(result, dict):
            out.append(f"  result 键={sorted(result.keys())}")
            for key in ("allMatch", "songs", "albums", "artists", "playlists", "order"):
                node = result.get(key)
                if isinstance(node, list):
                    out.append(f"    [{key}] {len(node)} 条")
                    for item in node[:5]:
                        if isinstance(item, dict):
                            out.append(f"       {json.dumps(item, ensure_ascii=False)[:150]}")
                elif node is not None:
                    out.append(f"    [{key}] {type(node).__name__}")
        elif result is not None:
            out.append(f"  result 是 {type(result).__name__}: {str(result)[:200]}")
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"已写入 {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
