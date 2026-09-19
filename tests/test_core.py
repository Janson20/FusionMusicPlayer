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


def test_credential_renew_window():
    """凭据续期窗口：临近过期才续，关掉时一律不续，老凭据补一次有效期。"""
    from app.sources.netease import COOKIE_TTL_SECONDS, should_renew

    now = 1_700_000_000
    day = 86400

    # 还剩 100 天：不续
    assert should_renew(now + 100 * day, now, 7) is False
    # 还剩 3 天：进入窗口
    assert should_renew(now + 3 * day, now, 7) is True
    # 已经过期 / 正好到点：续
    assert should_renew(now - day, now, 7) is True
    assert should_renew(now, now, 7) is True
    # 窗口边界：正好 7 天算进入窗口，多 1 秒就不算
    assert should_renew(now + 7 * day, now, 7) is True
    assert should_renew(now + 7 * day + 1, now, 7) is False
    # 关闭自动续期（0 或负数）：一律不续
    assert should_renew(now - day, now, 0) is False
    assert should_renew(now - day, now, -1) is False
    # 老版本凭据没有 expires_at：开着就补一次，关着就算了
    assert should_renew(0, now, 7) is True
    assert should_renew(0, now, 0) is False

    # 服务端给 MUSIC_U 的 Max-Age 是 180 天，兜底估算与它保持一致
    assert COOKIE_TTL_SECONDS == 180 * 24 * 3600


def test_album_title_matching():
    """专辑名核对：别的音源的 album_id 撞车时不能认（见 AlbumController）。"""
    from app.sources.netease import pick_album, same_title

    assert same_title("我是初音未来", "我是初音未来") is True
    assert same_title("我是初音未来 ", " 我是初音未来") is True      # 空白无关
    assert same_title("ABC", "abc") is True                          # 大小写无关
    assert same_title("我是初音未来", "我是初音未来（Deluxe）") is True  # 包含关系
    assert same_title("我是初音未来", "我是秦始皇") is False
    assert same_title("", "我是初音未来") is False
    assert same_title(None, None) is False

    albums = [
        {"id": "1", "name": "我是初音未来", "size": 2},
        {"id": "2", "name": "我是初音未来", "size": 12},
        {"id": "3", "name": "我是秦始皇", "size": 2},
    ]
    # 同名多张取曲目多的（通常是原版专辑，不是单曲版）
    assert pick_album(albums, "我是初音未来")["id"] == "2"
    # 名字互相包含也能挑中
    assert pick_album(albums, "初音")["id"] == "2"
    # 完全对不上时退化成第一个
    assert pick_album(albums, "完全无关的名字")["id"] == "1"
    assert pick_album([], "x") == {}


# ──────────────────────────────────────────────────────────────
# 歌曲百科
# ──────────────────────────────────────────────────────────────


def test_song_wiki_parsing():
    """百科区块解析：取值位置随字段类型而变，行顺序由客户端定。

    网易云把「语种 / BPM」放在 ``uiElement.textLinks``，「曲风 / 推荐标签」这类
    放在 ``resources[].uiElement.mainTitle``；而「发行时间 / 发行版本」根本不在
    这个接口里（来自专辑详情），要由客户端插在「语种」和「BPM」中间。
    """
    from app.sources.netease import parse_song_wiki

    payload = {
        "code": 200,
        "data": {
            "blocks": [
                {"code": "SONG_PLAY_ABOUT_MUSIC_MEMORY", "creatives": []},
                {
                    "code": "SONG_PLAY_ABOUT_SONG_BASIC",
                    "creatives": [
                        {
                            "creativeType": "songTag",
                            "uiElement": {"mainTitle": {"title": "曲风"}},
                            "resources": [
                                {"uiElement": {"mainTitle": {"title": "二次元-歌声合成"}}}
                            ],
                        },
                        {
                            "creativeType": "language",
                            "uiElement": {"mainTitle": {"title": "语种"},
                                           "textLinks": [{"text": "国语"}]},
                        },
                        {
                            "creativeType": "bpm",
                            "uiElement": {"mainTitle": {"title": "BPM"},
                                           "textLinks": [{"text": "59"}]},
                        },
                        {
                            "creativeType": "songBizTag",
                            "uiElement": {"mainTitle": {"title": "推荐标签"}},
                            "resources": [
                                {"uiElement": {"mainTitle": {"title": "思念"}}},
                                {"uiElement": {"mainTitle": {"title": "欢快"}}},
                            ],
                        },
                        # 乐谱块只是「上传乐谱」的入口，不是百科内容，必须丢掉
                        {
                            "creativeType": "sheet",
                            "uiElement": {"mainTitle": {"title": "暂无乐谱"}},
                        },
                    ],
                },
                # 同一个响应里还有相似歌曲 / 相关歌单，它们不属于音乐百科面板
                {
                    "code": "SONG_PLAY_ABOUT_SIMILAR_SONG",
                    "creatives": [
                        {"resources": [{"uiElement": {"mainTitle": {"title": "不相干的歌"}}}]}
                    ],
                },
            ]
        },
    }
    rows = parse_song_wiki(payload, {"publish_text": "2018-11-30",
                                     "version": "录音室版"})["rows"]

    assert [r["label"] for r in rows] == [
        "曲风", "语种", "发行时间", "发行版本", "BPM", "推荐标签",
    ]
    assert rows[0]["value"] == "二次元·歌声合成"  # 两级曲风画成「父类·子类」
    assert rows[2]["value"] == "2018-11-30"
    assert rows[3]["value"] == "录音室版"
    assert rows[5]["value"] == "思念、欢快"
    assert all("不相干的歌" not in r["value"] for r in rows)


def test_song_wiki_edge_cases():
    """没有数据时返回空字典（界面显示空态），有数据时服务端的标题优先。"""
    from app.sources.netease import parse_song_wiki

    assert parse_song_wiki({}) == {}
    assert parse_song_wiki(None) == {}
    assert parse_song_wiki({"data": {"blocks": []}}) == {}
    # 空壳 creative（有类型没内容）不算数据
    assert parse_song_wiki({"data": {"blocks": [
        {"code": "SONG_PLAY_ABOUT_SONG_BASIC", "creatives": [
            {"creativeType": "language", "uiElement": {"mainTitle": {"title": "语种"}}},
        ]},
    ]}}) == {}
    # 专辑那边拿到了发行信息，就算百科接口什么都没给，也算有内容
    assert parse_song_wiki({}, {"publish_text": "2020-01-01"})["rows"] == [
        {"label": "发行时间", "value": "2020-01-01"},
    ]

    # 多条曲风用「/」分开；服务端改了字段名这边跟着改
    payload = {"data": {"blocks": [{"code": "SONG_PLAY_ABOUT_SONG_BASIC", "creatives": [
        {
            "creativeType": "songTag",
            "uiElement": {"mainTitle": {"title": "风格"}},
            "resources": [
                {"uiElement": {"mainTitle": {"title": "流行-华语流行"}}},
                {"uiElement": {"mainTitle": {"title": "摇滚-流行摇滚"}}},
            ],
        },
    ]}]}}
    assert parse_song_wiki(payload)["rows"] == [
        {"label": "风格", "value": "流行·华语流行 / 摇滚·流行摇滚"},
    ]


def test_pick_wiki_song():
    """别的音源按名字找网易云的歌：歌名 + 时长两道关，完全同名的优先。"""
    from app.sources.base import MusicInfo
    from app.sources.netease import pick_wiki_song

    def mi(name, songmid, interval):
        return MusicInfo(name=name, singer="歌手", source="wy",
                         songmid=songmid, interval=interval)

    songs = [
        mi("晴天（深情版）", "1", 250),
        mi("晴天", "2", 300),
        mi("晴天", "3", 200),
    ]
    # 完全同名优先，哪怕它在结果里排后面
    assert pick_wiki_song(songs, "晴天", 300).songmid == "2"
    # 同名的时长都不对时，退到「名字互相包含」的那首
    assert pick_wiki_song(songs, "晴天", 250).songmid == "1"
    # 时长对得上就按同名 + 时长挑
    assert pick_wiki_song(songs, "晴天", 200).songmid == "3"
    # 时长对不上的一律不要（翻唱 / Live 就是这么被挡掉的）
    assert pick_wiki_song([mi("起风了", "7", 200)], "起风了", 325) is None

    # 没有时长可佐证时只认完全同名：否则「不存在的歌」会匹配到
    # 搜索结果里那个碰巧包含这几个字的名字
    assert pick_wiki_song(songs, "晴天", 0).songmid == "2"
    assert pick_wiki_song([mi("不存在的歌（Live）", "9", 180)], "不存在的歌", 0) is None
    assert pick_wiki_song([mi("不存在的歌（Live）", "9", 180)], "不存在的歌", 180).songmid == "9"

    # 空输入
    assert pick_wiki_song([], "晴天", 100) is None
    assert pick_wiki_song(songs, "", 100) is None


def test_roam_refill_rules():
    """漫游续歌的时机：早了会断，晚了会疯了一样往队列里塞歌。"""
    from app.core.roam import clean_reason, needs_refill, pick_playable

    # 没在漫游 / 已经在取了：一律不续
    assert needs_refill(False, 0, False) is False
    assert needs_refill(True, 0, True) is False
    # 队列里还剩很多：不续
    assert needs_refill(True, 10, False) is False
    assert needs_refill(True, 3, False) is False
    # 剩得不多（默认阈值 2）：续
    assert needs_refill(True, 2, False) is True
    assert needs_refill(True, 1, False) is True
    assert needs_refill(True, 0, False) is True
    assert needs_refill(True, -1, False) is True      # 队列算错了也别卡死
    # 阈值可以调，0 表示「一放完就续」
    assert needs_refill(True, 1, False, threshold=0) is False
    assert needs_refill(True, 0, False, threshold=0) is True

    # 推荐理由收拾成一小截
    assert clean_reason("  你关注的   音乐人新歌 ") == "你关注的 音乐人新歌"
    assert clean_reason("") == ""
    assert clean_reason(None) == ""
    long_reason = "根据你最近反复收听的口味为你挑选的一批歌曲"
    assert len(clean_reason(long_reason)) <= 16
    assert clean_reason(long_reason).endswith("…")

    # 过滤掉放不了的条目
    assert pick_playable([Track(source="wy", songmid="1", name="有歌名"),
                          Track(source="wy", songmid="", name="没 id"),
                          Track(source="wy", songmid="2", name=""),
                          None]) == [Track(source="wy", songmid="1", name="有歌名")]


def test_track_reason_is_transient():
    """推荐理由只用于展示，不能跟着歌单 / 收藏一起落盘。"""
    track = Track(source="wy", songmid="1", name="歌", reason="你关注的音乐人新歌")
    assert track.reason == "你关注的音乐人新歌"
    assert "reason" not in track.to_dict()
    # 走一遍「落盘 → 读回」：理由不该被带回来
    again = Track.from_dict(track.to_dict())
    assert again.reason == ""
    assert again.name == "歌"


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
