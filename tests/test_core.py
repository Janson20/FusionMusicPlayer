"""核心逻辑回归测试（不依赖 Qt 界面、不联网）。

运行方式::

    python tests/test_core.py        # 直接运行
    pytest tests/test_core.py        # 或交给 pytest

覆盖：凭据加密仓库、LRC 解析与翻译配对、播放队列与四种播放模式。
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.lyrics import parse_lyrics  # noqa: E402
from app.core.models import Track, format_duration  # noqa: E402
from app.core.queue import PlayMode, PlayQueue, mode_from_name  # noqa: E402
from app.security.vault import CredentialVault  # noqa: E402


# ──────────────────────────────────────────────────────────────
# 凭据加密仓库
# ──────────────────────────────────────────────────────────────


def test_vault_roundtrip():
    tmp = Path(tempfile.mkdtemp(prefix="fusion_vault_"))
    v = CredentialVault(tmp / "credentials.enc")
    payload = {
        "provider": "netease",
        "cookies": "MUSIC_U=abc123; __csrf=xyz; os=pc",
        "nickname": "测试用户",
        "user_id": 42,
    }
    assert v.save(payload) is True
    assert (tmp / "credentials.enc").exists()

    raw = (tmp / "credentials.enc").read_text(encoding="utf-8")
    # 明文绝不能落盘
    assert "MUSIC_U=abc123" not in raw
    # 信封必须自描述，便于以后换算法
    envelope = json.loads(raw)
    assert envelope["format_version"] == 1
    assert envelope["cipher"] == "aes-256-gcm"
    assert envelope["kdf"] in ("hkdf-sha256", "pbkdf2-sha256")

    again = CredentialVault(tmp / "credentials.enc")
    assert again.load() == payload


def test_vault_detects_tampering():
    tmp = Path(tempfile.mkdtemp(prefix="fusion_vault_"))
    v = CredentialVault(tmp / "credentials.enc")
    v.save({"cookies": "MUSIC_U=secret"})

    env = json.loads((tmp / "credentials.enc").read_text(encoding="utf-8"))
    env["payload"] = env["payload"][:-8] + "AAAAAAAA"
    (tmp / "credentials.enc").write_text(json.dumps(env), encoding="utf-8")

    # 认证加密：篡改必然失败，且绝不把密文当明文返回
    assert CredentialVault(tmp / "credentials.enc").load() is None


def test_vault_missing_file():
    tmp = Path(tempfile.mkdtemp(prefix="fusion_vault_"))
    v = CredentialVault(tmp / "nope.enc")
    assert v.exists() is False
    assert v.load() is None


# ──────────────────────────────────────────────────────────────
# 歌词
# ──────────────────────────────────────────────────────────────


def test_lyrics_basic():
    ly = parse_lyrics("[ti:Test]\n[00:01.50]第一行\n[00:02.5]第二行\n")
    assert len(ly.lines) == 2
    # 毫秒位不足 3 位时右侧补零
    assert ly.lines[0].time == 1500
    assert ly.lines[1].time == 2500


def test_lyrics_offset_and_multi_tag():
    ly = parse_lyrics("[offset:100]\n[00:01.50]A\n[00:03.00][00:05.00]B\n")
    assert ly.lines[0].time == 1600
    assert ly.lines[1].time == 3100
    assert ly.lines[2].time == 5100
    assert ly.lines[1].text == ly.lines[2].text == "B"


def test_lyrics_negative_offset_is_clamped():
    ly = parse_lyrics("[offset:-5000]\n[00:01.00]A\n")
    assert ly.lines[0].time == 0


def test_lyrics_translation_pairs_when_sub_has_no_offset():
    ly = parse_lyrics("[offset:100]\n[00:01.50]A\n[00:05.00]B\n")
    ly.set_translation("[00:01.50]translated-A\n[00:05.00]translated-B\n")
    assert ly.lines[0].translation == "translated-A"
    assert ly.lines[1].translation == "translated-B"


def test_lyrics_index_at_uses_next_line_boundary():
    ly = parse_lyrics("[00:01.00]A\n[00:04.00]B\n[00:10.00]C\n")
    assert ly.index_at(500) == -1          # 第一行之前
    assert ly.index_at(1000) == 0
    assert ly.index_at(3900) == 0          # 仍在 A 行
    assert ly.index_at(4000) == 1          # 已进入 B 行
    assert ly.index_at(10000) == 2
    # 连续查询要走缓存且结果正确
    assert ly.index_at(12000) == 2
    assert ly.index_at(2000) == 0


def test_lyrics_word_level():
    ly = parse_lyrics("[00:01.00]<0,300>你<300,300>好\n")
    assert ly.lines[0].is_word_based
    assert [w.text for w in ly.lines[0].words] == ["你", "好"]


def test_lyrics_empty():
    ly = parse_lyrics(None)
    assert ly.is_empty and ly.index_at(0) == -1
    assert ly.parse("") is False


# ──────────────────────────────────────────────────────────────
# 队列与播放模式
# ──────────────────────────────────────────────────────────────


def make_tracks(n: int):
    return [
        Track(source="wy", songmid=str(i), name=f"T{i}", singer="S", interval=200)
        for i in range(n)
    ]


def test_queue_set_and_index():
    q = PlayQueue()
    q.set_tracks(make_tracks(5), 2)
    assert q.size == 5
    assert q.index == 2
    assert q.current().name == "T2"
    assert q.at(99) is None


def test_mode_from_name():
    assert mode_from_name("shuffle") == PlayMode.SHUFFLE
    assert mode_from_name("loop_single") == PlayMode.LOOP_SINGLE
    assert mode_from_name("bogus") == PlayMode.LOOP_LIST
    assert mode_from_name("") == PlayMode.LOOP_LIST


def test_order_mode():
    q = PlayQueue()
    q.set_tracks(make_tracks(3), 0)
    q.mode = PlayMode.ORDER
    # 手动切歌回绕
    assert q.next_index(manual=True) == 1
    q.set_index(2)
    # 自然播完到末尾即停
    assert q.next_index(auto_advance=True) is None
    assert q.next_index(manual=True) == 0
    # 「上一首」回溯的是真实播放历史（0 -> 2），而不是简单的下标 -1
    assert q.prev_index() == 0
    q.set_index(1)
    assert q.prev_index() == 2


def test_loop_list_mode():
    q = PlayQueue()
    q.set_tracks(make_tracks(3), 2)
    q.mode = PlayMode.LOOP_LIST
    assert q.next_index(auto_advance=True) == 0
    assert q.next_index(manual=True) == 0


def test_single_mode():
    q = PlayQueue()
    q.set_tracks(make_tracks(4), 1)
    q.mode = PlayMode.LOOP_SINGLE
    # 单曲循环只在自然播完时重播
    assert q.next_index(auto_advance=True) == 1
    # 手动切歌仍然前进
    assert q.next_index(manual=True) == 2


def test_shuffle_is_a_permutation():
    q = PlayQueue()
    q.set_tracks(make_tracks(8), 0)
    q.mode = PlayMode.SHUFFLE
    # 当前曲目排在随机序列首位，因此接下来 7 次应恰好覆盖其余 7 首且不重复
    seen = []
    for _ in range(7):
        idx = q.next_index(auto_advance=True)
        seen.append(idx)
        q.set_index(idx, record_history=False)
    assert len(set(seen)) == 7
    assert 0 not in seen
    # 一轮结束后会重新洗牌并继续
    assert q.next_index(auto_advance=True) is not None


def test_history_backtracking():
    q = PlayQueue()
    q.set_tracks(make_tracks(6), 0)
    q.set_index(3)
    q.set_index(5)
    assert q.prev_index() == 3


def test_insert_and_move():
    q = PlayQueue()
    q.set_tracks(make_tracks(4), 1)
    extra = Track(source="wy", songmid="99", name="NEXT")
    q.insert_next(extra)
    assert q.at(q.index + 1).songmid == "99"
    assert q.size == 5

    before = [t.name for t in q.tracks()]
    assert q.move(0, 3) is True
    after = [t.name for t in q.tracks()]
    assert before != after and sorted(before) == sorted(after)
    assert q.size == 5


def test_remove_keeps_index_sane():
    q = PlayQueue()
    q.set_tracks(make_tracks(4), 2)
    q.remove_at(0)
    assert q.index == 1 and q.size == 3
    q.remove_at(1)
    assert 0 <= q.index < q.size


def test_queue_serialization():
    q = PlayQueue()
    q.set_tracks(make_tracks(3), 1)
    q.mode = PlayMode.SHUFFLE
    data = q.to_dict()

    q2 = PlayQueue()
    q2.load_dict(data)
    assert q2.size == 3
    assert q2.mode == PlayMode.SHUFFLE
    assert q2.index == 1


# ──────────────────────────────────────────────────────────────
# 曲目模型
# ──────────────────────────────────────────────────────────────


def test_track_uid_and_dict():
    t = Track(source="wy", songmid="123", name="歌", singer="手", interval=65)
    assert t.uid == "wy:123"
    assert t.duration_text == "1:05"

    d = t.to_dict()
    # QML 侧直接读字典，派生字段必须带上
    for key in ("uid", "durationText", "sourceText", "isLocal", "bestQuality", "displayName"):
        assert key in d, key
    assert d["durationText"] == "1:05"

    back = Track.from_dict(d)
    assert back.uid == t.uid and back.name == t.name


def test_track_from_dict_ignores_unknown_keys():
    t = Track.from_dict({"source": "tx", "songmid": "1", "name": "A", "bogus": 1})
    assert t.source == "tx" and t.name == "A"
    assert Track.from_dict(None).name == ""


def test_track_same_song():
    a = Track(source="wy", songmid="1", name="A")
    b = Track(source="wy", songmid="1", name="A (Live)")
    c = Track(source="tx", songmid="1", name="A")
    assert a.same_song(b) is True
    assert a.same_song(c) is False


def test_format_duration():
    assert format_duration(0) == "0:00"
    assert format_duration(-5) == "0:00"
    assert format_duration(59) == "0:59"
    assert format_duration(60) == "1:00"
    assert format_duration(3599) == "59:59"
    assert format_duration(3600) == "1:00:00"
    assert format_duration("bad") == "0:00"


# ──────────────────────────────────────────────────────────────
# 网易云会员识别
# ──────────────────────────────────────────────────────────────


def test_vip_flags_from_type():
    from app.sources.netease import vip_flags_from_type

    # 未登录 / 无会员
    assert vip_flags_from_type(0) == (False, False, False)
    assert vip_flags_from_type(None) == (False, False, False)
    assert vip_flags_from_type("bad") == (False, False, False)

    # account.vipType 是标量：11 = 黑胶VIP + 音乐包
    assert vip_flags_from_type(11) == (False, True, True)
    assert vip_flags_from_type(10) == (False, True, False)
    assert vip_flags_from_type(1) == (False, False, True)

    # profile.vipType 是位掩码：110 = SVIP | 黑胶VIP
    # 上游只读这个字段，拿 110 去查标签表落到「普通用户」——就是这个 bug
    assert vip_flags_from_type(110) == (True, True, False)
    assert vip_flags_from_type(100) == (True, True, False)
    assert vip_flags_from_type(111) == (True, True, True)

    # 文档记载的标量 20 也是 SVIP
    assert vip_flags_from_type(20) == (True, True, False)


if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:
            failed.append(name)
            print(f"FAIL  {name}: {e}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        print("failed:", ", ".join(failed))
    sys.exit(1 if failed else 0)
