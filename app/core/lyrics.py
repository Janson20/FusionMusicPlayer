"""LRC 歌词解析。

三个正则与时间计算规则逐字沿用 FMCL ``ui/music_lyrics.py``，保证与既有行为一致：

* ``[mm:ss.xx]`` 时间标签，毫秒位不足 3 位时右侧补零（``.5`` → ``500``）
* 一行带多个时间标签时展开为多行
* 全局 ``[offset:]`` 在最后叠加，负值钳到 0
* 支持 ``<mm:ss,ms>`` 形式的逐字歌词

相对 FMCL 的增强：
* 翻译（tlyric）与罗马音（romalrc）**真正接上**——FMCL 解析了却从不显示；
* 配对同时支持「时间戳精确相等」与「±80 ms 容差」两种情形；
* 提供 :meth:`Lyrics.index_at` 供 QML 歌词列表高亮，内部带缓存。
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_TIME_TAG_RE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_WORD_TAG_RE = re.compile(r"<(-?\d+),(-?\d+)(?:,-?\d+)?>")
_META_TAG_RE = re.compile(r"\[(ti|ar|al|offset|by|kuwo|tool|length):\s*(.*?)\s*\]", re.IGNORECASE)

# 翻译/罗马音配对的时间容差（毫秒）
PAIR_TOLERANCE_MS = 150
# 无逐字信息时一行的默认持续时间
DEFAULT_LINE_MS = 5000


@dataclass
class LyricWord:
    """逐字歌词的一个片段。"""

    text: str
    start: int  # 毫秒
    duration: int  # 毫秒

    @property
    def end(self) -> int:
        return self.start + self.duration


@dataclass
class LyricLine:
    text: str
    time: int  # 毫秒
    translation: str = ""
    roma: str = ""
    words: List[LyricWord] = field(default_factory=list)

    @property
    def is_word_based(self) -> bool:
        return bool(self.words)

    @property
    def end_time(self) -> int:
        if self.words:
            return self.words[-1].end
        return self.time + DEFAULT_LINE_MS

    @property
    def has_sub(self) -> bool:
        return bool(self.translation or self.roma)

    @property
    def sub_text(self) -> str:
        return self.translation or self.roma


class Lyrics:
    """解析后的歌词集合。"""

    def __init__(self) -> None:
        self.lines: List[LyricLine] = []
        self.tags: Dict[str, str] = {}
        self.offset_ms: int = 0
        self._times: List[int] = []
        self._cache_key: int = -10_000
        self._cache_index: int = -1

    # ── 解析 ────────────────────────────────────────────────

    def clear(self) -> None:
        self.lines.clear()
        self.tags.clear()
        self.offset_ms = 0
        self._times.clear()
        self._cache_key = -10_000
        self._cache_index = -1

    @property
    def is_empty(self) -> bool:
        return not self.lines

    def parse(self, raw_text: Optional[str]) -> bool:
        """解析 LRC 文本，返回是否解析出至少一行。"""
        self.clear()
        if not raw_text:
            return False

        # 第一遍：收集元信息标签
        for line in raw_text.splitlines():
            for m in _META_TAG_RE.finditer(line):
                self.tags[m.group(1).lower()] = m.group(2)
        try:
            self.offset_ms = int(float(self.tags.get("offset", "0") or 0))
        except (TypeError, ValueError):
            self.offset_ms = 0

        # 第二遍：解析正文
        for line in raw_text.splitlines():
            self.lines.extend(self._parse_line(line))

        self.lines.sort(key=lambda l: l.time)
        self._times = [l.time for l in self.lines]
        self._cache_key = -10_000
        self._cache_index = -1
        return bool(self.lines)

    def _parse_line(self, line: str) -> List[LyricLine]:
        out: List[LyricLine] = []
        line = line.strip()
        if not line:
            return out
        time_matches = list(_TIME_TAG_RE.finditer(line))
        if not time_matches:
            return out

        stripped = line
        for m in time_matches:
            stripped = stripped.replace(m.group(0), "", 1)

        plain = _WORD_TAG_RE.sub("", stripped).strip()
        if not plain:
            return out

        words: List[LyricWord] = []
        if _WORD_TAG_RE.search(stripped):
            words = _parse_words(stripped)

        for tm in time_matches:
            try:
                minutes = int(tm.group(1))
                seconds = int(tm.group(2))
                ms_str = tm.group(3) or "0"
                milliseconds = int(ms_str.ljust(3, "0")[:3])
            except (TypeError, ValueError):
                continue
            t = (minutes * 60 + seconds) * 1000 + milliseconds + self.offset_ms
            out.append(
                LyricLine(
                    text=plain,
                    time=max(0, t),
                    words=[LyricWord(w.text, max(0, w.start + self.offset_ms), w.duration) for w in words],
                )
            )
        return out

    # ── 翻译 / 罗马音 ───────────────────────────────────────

    def set_translation(self, raw: Optional[str]) -> None:
        self._merge(raw, "translation")

    def set_roma(self, raw: Optional[str]) -> None:
        self._merge(raw, "roma")

    def _merge(self, raw: Optional[str], attr: str) -> None:
        if not raw or not self.lines:
            return
        sub = Lyrics()
        sub.parse(raw)
        if not sub.lines:
            return
        # 翻译/罗马音常常不带自己的 [offset:]，此时沿用主歌词的偏移，
        # 否则整段会整体错位而配不上。
        shift = self.offset_ms - sub.offset_ms
        if shift:
            for line in sub.lines:
                line.time = max(0, line.time + shift)
        lookup = {l.time: l.text for l in sub.lines}
        sub_times = sorted(lookup)
        for line in self.lines:
            text = lookup.get(line.time)
            if not text:
                text = _nearest_text(lookup, sub_times, line.time, PAIR_TOLERANCE_MS)
            if text:
                setattr(line, attr, text)

    # ── 查询 ────────────────────────────────────────────────

    def index_at(self, elapsed_ms: int) -> int:
        """返回当前应高亮的行下标，无匹配返回 ``-1``。"""
        if not self.lines:
            return -1
        if elapsed_ms < self.lines[0].time:
            return -1
        # 缓存命中判定必须用「下一行的起始时间」而不是 end_time：
        # end_time 在一行只有 5 秒默认时长时会把后续几秒都算作同一行。
        i = self._cache_index
        if 0 <= i < len(self.lines) and self.lines[i].time <= elapsed_ms:
            nxt = self.lines[i + 1].time if i + 1 < len(self.lines) else None
            if nxt is None or elapsed_ms < nxt:
                return i
        idx = bisect.bisect_right(self._times, elapsed_ms) - 1
        if idx < 0:
            return -1
        self._cache_key = elapsed_ms
        self._cache_index = idx
        return idx

    def line_at(self, elapsed_ms: int) -> Optional[LyricLine]:
        idx = self.index_at(elapsed_ms)
        return self.lines[idx] if idx >= 0 else None

    def window(self, elapsed_ms: int, before: int = 2, after: int = 6) -> List[Tuple[int, LyricLine]]:
        """返回当前行前后的一段歌词（供 UI 局部刷新）。"""
        idx = self.index_at(elapsed_ms)
        if idx < 0:
            return [(i, l) for i, l in enumerate(self.lines[: max(0, after)])]
        lo = max(0, idx - before)
        hi = min(len(self.lines), idx + after + 1)
        return [(i, self.lines[i]) for i in range(lo, hi)]

    def to_dicts(self) -> List[Dict[str, object]]:
        return [
            {
                "text": l.text,
                "time": l.time,
                "translation": l.translation,
                "roma": l.roma,
                "sub": l.sub_text,
            }
            for l in self.lines
        ]


def _nearest_text(lookup: Dict[int, str], times: List[int], target: int, tolerance: int) -> str:
    """在容差范围内取时间最接近的一条。"""
    pos = bisect.bisect_left(times, target)
    best = ""
    best_delta = tolerance + 1
    for i in (pos - 1, pos):
        if 0 <= i < len(times):
            delta = abs(times[i] - target)
            if delta <= tolerance and delta < best_delta:
                best_delta = delta
                best = lookup[times[i]]
    return best


def _parse_words(text: str) -> List[LyricWord]:
    """解析 ``<start,duration>字`` 形式的逐字歌词。"""
    parts = re.split(r"(<-?\d+,-?\d+(?:,-?\d+)?>)", text)
    words: List[LyricWord] = []
    last_end = 0
    for part in parts:
        m = _WORD_TAG_RE.fullmatch(part)
        if m:
            last_end = int(m.group(1))
            continue
        if not part:
            continue
        if not part.strip():
            continue
        start = last_end
        words.append(LyricWord(part, start, 300))
        last_end = start + 300
    # 合并起点相同的相邻片段
    merged: List[LyricWord] = []
    for w in words:
        if merged and merged[-1].start == w.start:
            merged[-1].text += w.text
            merged[-1].duration = max(merged[-1].duration, w.duration)
        else:
            merged.append(w)
    return merged


def parse_lyrics(raw: Optional[str], translation: Optional[str] = None,
                 roma: Optional[str] = None) -> Lyrics:
    """便捷入口：一次性解析主歌词 + 翻译 + 罗马音。"""
    ly = Lyrics()
    ly.parse(raw)
    if translation:
        ly.set_translation(translation)
    if roma:
        ly.set_roma(roma)
    return ly
