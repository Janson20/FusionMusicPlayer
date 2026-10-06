"""探测：各音源能取到什么形态的歌词（尤其是**逐字**歌词）。

用法::

    python tools/probe_word_lyrics.py [歌名] [输出文件]

为什么需要它：动态歌词能不能做，取决于「有多少歌真的下发逐字歌词」。实测
（2026-10）网易云约三成歌曲有，所以界面上必须有伪动态兜底；这个脚本用来
复查这个结论、以及接口有没有变。

* 网易云：走 ``sources/netease.py:fetch_lyric_bundle``（逐行 / 翻译 / 罗马音 /
  逐字一次取回），打印各字段长度与 yrc 的前几行；
* 其它音源：只打印歌词文本的形态（确认它们给的是纯 LRC）。

输出统一写 UTF-8 文件（Windows 控制台是 GBK，中文会炸）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sources import get_source, search_one  # noqa: E402

OUT: list[str] = []


def say(text: str = "") -> None:
    OUT.append(str(text))


def preview(text: str, lines: int = 3, width: int = 200) -> str:
    if not text:
        return "(空)"
    body = [ln for ln in str(text).splitlines() if ln.strip()][:lines]
    return "\n      ".join(ln[:width] for ln in body)


def probe_netease(keyword: str) -> None:
    from app.sources.netease import fetch_lyric_bundle

    say("=" * 78)
    say("网易云")
    items = search_one("wy", keyword, 1, 5) or []
    if not items:
        say("  搜索无结果")
        return
    hit = 0
    for info in items:
        bundle = fetch_lyric_bundle(str(info.songmid))
        if bundle is None:
            say(f"  {info.name} - {info.singer}: 接口没返回可用歌词")
            continue
        mark = "★ 逐字" if bundle.word else "  逐行"
        if bundle.word:
            hit += 1
        say(f"  {mark} {info.name} - {info.singer} (id={info.songmid})")
        say(f"        lrc={len(bundle.lrc)} tlyric={len(bundle.translation)} "
            f"romalrc={len(bundle.roma)} yrc={len(bundle.word)} "
            f"ytlyric={len(bundle.word_translation)}")
        if bundle.word:
            lines = [ln for ln in bundle.word.splitlines() if ln.strip()]
            for line in lines[:2]:
                say(f"        |{line[:170]}")
        else:
            say(f"        lrc 首行 |{(bundle.lrc.splitlines() or [''])[0][:120]}")
    say(f"  小结：{hit}/{len(items)} 首有逐字歌词（yrc）")


def probe_others(keyword: str) -> None:
    for sid, name in (("tx", "QQ音乐"), ("kw", "酷我"), ("kg", "酷狗"), ("mg", "咪咕")):
        say("=" * 78)
        say(name)
        items = search_one(sid, keyword, 1, 2) or []
        if not items:
            say("  搜索无结果")
            continue
        info = items[0]
        src = get_source(sid)
        try:
            text = src.get_lyric(info) if src else None
        except Exception as e:
            say(f"  {info.name}: 取歌词失败 {type(e).__name__}: {e}")
            continue
        say(f"  {info.name} - {info.singer}  歌词长度={len(text or '')}")
        say(f"      {preview(text or '')}")


def main() -> int:
    keyword = sys.argv[1] if len(sys.argv) > 1 else "起风了"
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("word_lyrics_probe.txt")
    say(f"关键词: {keyword}")
    probe_netease(keyword)
    probe_others(keyword)
    target.write_text("\n".join(OUT), encoding="utf-8")
    print(f"已写入 {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
