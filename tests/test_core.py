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

from app.core.lyrics import Lyrics, parse_lyrics  # noqa: E402
from app.core.models import Track, format_duration  # noqa: E402
from app.core.queue import PlayMode, PlayQueue, mode_from_name  # noqa: E402
from app.security.vault import CredentialVault  # noqa: E402

#: 跑 JS 库（ArtistNames.js）时用的 QCoreApplication，**必须留住引用**：
#: 被 Python 回收掉之后 Qt 会对着已销毁的实例干活（实测直接崩）
_QT_APP = None


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
# 便携模式（凭据能不能跟着程序目录换台电脑）
# ──────────────────────────────────────────────────────────────


class _PortableFixture:
    """给便携模式用例准备一个独立的数据目录 + 一份凭据。

    ``paths.set_data_dir`` 与密钥偏好都是模块级的全局量，退出时都要还原，
    否则会漏到别的用例里。
    """

    CREDS = {
        "provider": "netease",
        "cookies": "MUSIC_U=secret; __csrf=x",
        "user_id": 42,
        "nickname": "测试用户",
    }

    def __enter__(self):
        import sys

        from app import paths

        self.paths = paths
        self.module = sys.modules["app.security.vault"]
        self.previous_dir = paths._DATA_DIR_OVERRIDE  # noqa: SLF001 - 只为还原
        self.previous_pref = self.module.portable_preference()
        self.root = Path(tempfile.mkdtemp(prefix="fusion_portable_"))
        paths.set_data_dir(self.root / "data")
        self._real_protect = self.module._dpapi_protect  # noqa: SLF001
        self._real_unprotect = self.module._dpapi_unprotect  # noqa: SLF001
        return self

    def __exit__(self, *exc):
        self.module._dpapi_protect = self._real_protect  # noqa: SLF001
        self.module._dpapi_unprotect = self._real_unprotect  # noqa: SLF001
        self.module.set_portable_preference(self.previous_pref)
        self.paths.set_data_dir(self.previous_dir)
        return False

    def vault(self):
        return CredentialVault(self.root / "data" / "credentials.enc")

    def key_bytes(self) -> bytes:
        return self.paths.key_file().read_bytes()

    def break_dpapi(self) -> None:
        """模拟「换了台电脑 / 换了个 Windows 用户」：DPAPI 既包不上也解不开。"""
        self.module._dpapi_protect = lambda data: None  # noqa: SLF001
        self.module._dpapi_unprotect = lambda data: None  # noqa: SLF001


def test_vault_portable_switch_keeps_the_key():
    """便携模式只换**密钥文件的存法**，不换密钥本身 —— 所以开关可以随时拨，
    已经登录的凭据照样解得开，不需要重新登录。"""
    from app.security.vault import PORTABLE_MAGIC

    with _PortableFixture() as fx:
        v = fx.vault()
        assert v.save(fx.CREDS) is True
        assert v.key_usable() is True
        assert v.portable() is False
        fingerprint = v.key_fingerprint()

        # 打开：文件头变成 PORT + 裸密钥
        assert v.set_portable(True) == "portable"
        assert fx.key_bytes()[:4] == PORTABLE_MAGIC
        assert len(fx.key_bytes()) == 4 + 32
        assert v.portable() is True and v.key_usable() is True
        # 密钥没变（指纹一致），旧凭据照样解得开
        assert v.key_fingerprint() == fingerprint
        assert v.load() == fx.CREDS

        # 关掉：重新由本机 DPAPI 包裹，密钥依然是同一个
        expected = "dpapi" if fx.module.dpapi_available() else "keyfile"
        assert v.set_portable(False) == expected
        assert v.key_fingerprint() == fingerprint
        assert v.load() == fx.CREDS


def test_vault_portable_survives_machine_move():
    """换台电脑：便携模式的凭据解得开，绑本机的解不开（这正是那个开关的意义）。"""
    from app.security.vault import PORTABLE_MAGIC

    with _PortableFixture() as fx:
        v = fx.vault()
        assert v.save(fx.CREDS) is True
        assert v.set_portable(True) == "portable"
        assert fx.key_bytes()[:4] == PORTABLE_MAGIC

        fx.break_dpapi()
        moved = fx.vault()          # 相当于在新机器上重新打开这个数据目录
        assert moved.portable() is True
        assert moved.key_usable() is True
        assert moved.load() == fx.CREDS


def test_vault_machine_bound_key_fails_loudly():
    """对照组：没开便携模式、密钥由别的机器保护时，必须报错而不是悄悄重建。

    报错信息里要点名那个开关，否则用户只能靠「手动删文件」自救。
    """
    from app.security.vault import VaultError

    with _PortableFixture() as fx:
        v = fx.vault()
        assert v.save(fx.CREDS) is True
        if not fx.module.dpapi_available():
            # 非 Windows 平台存的就是裸密钥，压根没有「绑本机」这回事
            assert v.portable() is True and v.key_usable() is True
            return

        assert v.set_portable(False) == "dpapi"
        assert fx.key_bytes()[:4] == b"DPA1"
        fx.break_dpapi()

        moved = fx.vault()
        assert moved.portable() is False
        assert moved.key_usable() is False
        assert moved.key_source() == "不可用"
        try:
            moved.load()
            raise AssertionError("绑在本机的密钥不该能在别处解开")
        except VaultError as e:
            assert "便携模式" in str(e)
        # 解不开就换不了存法：绝不能悄悄把密钥换掉（旧密钥可能还能在原机器上救回来）
        try:
            moved.set_portable(True)
            raise AssertionError("解不开的密钥不该被静默替换")
        except VaultError:
            pass
        assert fx.key_bytes()[:4] == b"DPA1"    # 文件没被动过


def test_vault_rebuild_key():
    """密钥解不开时的出路：重建密钥（旧密钥留备份、失效凭据清掉、之后能重新登录）。"""
    from app.security.vault import VaultError

    with _PortableFixture() as fx:
        v = fx.vault()
        assert v.save(fx.CREDS) is True

        # 伪造成「从别的 Windows 用户那儿拷过来的 DPAPI 密钥」
        fx.paths.key_file().write_bytes(b"DPA1" + b"\x00" * 60)
        moved = fx.vault()
        assert moved.key_usable() is False
        try:
            moved.load()
            raise AssertionError("不该解开")
        except VaultError:
            pass

        # 重建：按偏好（这里先打开便携模式）重新生成密钥
        fx.module.set_portable_preference(True)
        assert moved.rebuild_key() == "portable"
        assert moved.key_usable() is True and moved.portable() is True
        # 旧密钥不是删掉而是改名留档：回到原来那台机器还能救回来
        backup = fx.paths.key_file().with_name("master.key.unreadable")
        assert backup.exists() and backup.read_bytes()[:4] == b"DPA1"
        # 拿旧密钥加密的凭据已经作废，留着只会每次启动都报一次解密失败
        assert (fx.root / "data" / "credentials.enc").exists() is False
        # 现在能正常保存了
        assert moved.save(fx.CREDS) is True
        assert moved.load() == fx.CREDS


def test_vault_portable_preference_when_key_missing():
    """密钥还没生成时，portable() 按**偏好**回答 —— 否则用户还没登录过的话，
    设置页会把刚打开的开关显示成关着的。"""
    with _PortableFixture() as fx:
        assert fx.paths.key_file().exists() is False
        v = fx.vault()
        fx.module.set_portable_preference(True)
        assert v.portable() is True
        assert v.key_usable() is True          # 还没生成不算「不可用」
        # 开关本身不该顺手把密钥造出来（保持数据目录干净）
        assert fx.paths.key_file().exists() is False

        fx.module.set_portable_preference(False)
        assert v.portable() is False


def test_vault_path_follows_data_dir():
    """凭据文件必须跟着数据目录走。

    ``--data-dir`` / ``FUSION_MUSIC_HOME`` 改的是数据目录，而模块级单例是在
    ``import`` 时就建好的：早先把路径写死成实例属性，于是凭据留在老位置、
    主密钥跟着新目录走，两者分了家 ——「拷贝目录带走登录状态」就成了空话。
    """
    from app import paths
    from app.security.vault import CredentialVault

    previous = paths._DATA_DIR_OVERRIDE  # noqa: SLF001 - 只为还原
    root = Path(tempfile.mkdtemp(prefix="fusion_datadir_"))
    try:
        paths.set_data_dir(root)
        # 注意：set_data_dir 会 resolve（Windows 上临时目录可能带 8.3 短名），
        # 所以拿 paths.data_dir() 比，不要拿传进去的 root 比
        v = CredentialVault()          # 不传路径 = 用默认（数据目录）
        assert v.path == paths.data_dir() / "credentials.enc"
        # 密钥与凭据必须在同一个数据目录下
        assert v.path.parent == paths.key_file().parent.parent
        assert v.save({"provider": "netease", "cookies": "x"}) is True
        assert v.path.exists()

        # 目录再改，同一个实例要跟着换
        first = v.path
        paths.set_data_dir(root / "other")
        assert v.path == paths.data_dir() / "credentials.enc"
        assert v.path != first
        assert v.load() is None
    finally:
        paths.set_data_dir(previous)


# ──────────────────────────────────────────────────────────────
# 歌手名的拆分（本地标签 / 老曲库迁移）
# ──────────────────────────────────────────────────────────────


def test_normalize_singers():
    """歌手字段里的多名字分隔符统一成「、」。

    在线各源都会过 ``sources/utils.py:format_singer``，本地文件的原始标签一直少了
    这一步 —— 标签写着「洛天依/乐正绫」时界面按「、」去拆、拆出来还是一个歌手，
    看起来是一串、点进去还会去找这个不存在的歌手。
    """
    from app.core.models import normalize_singers

    assert normalize_singers("洛天依/乐正绫") == "洛天依、乐正绫"
    assert normalize_singers("洛天依&乐正绫") == "洛天依、乐正绫"
    assert normalize_singers("洛天依;乐正绫") == "洛天依、乐正绫"
    assert normalize_singers("哔哩哔哩拜年纪/洛天依/hanser") == "哔哩哔哩拜年纪、洛天依、hanser"
    # 幂等：在线音源来的值本来就是「、」拼的，读盘时再走一遍不会变样
    assert normalize_singers("洛天依、乐正绫") == "洛天依、乐正绫"
    assert normalize_singers("洛天依") == "洛天依"
    assert normalize_singers("") == "" and normalize_singers(None) == ""


def test_local_tags_normalize_singers():
    """扫描本地文件时就把歌手拆开，而不是留到界面上想办法。"""
    import tempfile
    from pathlib import Path

    from mutagen.id3 import ID3, TPE1, TIT2

    from app.core.resolver import resolve_local_metadata

    tmp = Path(tempfile.mkdtemp(prefix="fusion_singer_"))
    path = tmp / "song.mp3"
    header = b"\xff\xfb\x90\x00"
    path.write_bytes((header + b"\x00" * (417 - len(header))) * 40)
    tags = ID3()
    tags.add(TIT2(encoding=3, text="霜雪千年"))
    tags.add(TPE1(encoding=3, text="洛天依/乐正绫"))
    tags.save(str(path))

    track = resolve_local_metadata(str(path))
    assert track.name == "霜雪千年"
    assert track.singer == "洛天依、乐正绫"
    # 界面按「、」拆，拆出来必须是**两个**歌手（这就是「两个歌手变成一个」那条）
    assert [p for p in track.singer.split("、") if p] == ["洛天依", "乐正绫"]


def test_stored_singers_are_migrated_on_load():
    """老曲库 / 老的收藏与历史里存着未归一化的歌手：读盘时顺手修好。

    不修的话用户得为了这个重新扫一遍曲库，而且「我喜欢的音乐」「最近播放」里的
    本地歌同样中招。
    """
    import json
    import tempfile
    from pathlib import Path

    from app.core.store import Library

    root = Path(tempfile.mkdtemp(prefix="fusion_migrate_"))
    raw_track = {"source": "local", "songmid": "x.mp3", "name": "歌",
                 "singer": "洛天依/乐正绫", "path": "x.mp3"}
    (root / "local.json").write_text(json.dumps([raw_track]), encoding="utf-8")
    (root / "favorites.json").write_text(json.dumps([raw_track]), encoding="utf-8")
    (root / "playlists.json").write_text(
        json.dumps({"version": 1, "playlists": [
            {"id": "pl_test", "name": "自建歌单", "songs": [raw_track]},
        ]}),
        encoding="utf-8",
    )

    lib = Library(root)
    lib.load()
    assert lib.local_tracks()[0].singer == "洛天依、乐正绫"
    assert lib.favorites()[0].singer == "洛天依、乐正绫"
    playlist = lib.get_playlist("pl_test")
    assert playlist is not None and playlist.songs[0].singer == "洛天依、乐正绫"


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
# 播放会话（启动时恢复上次的队列与在播曲目）
# ──────────────────────────────────────────────────────────────


def test_session_roundtrip():
    from app.core import session as play_session

    tmp = Path(tempfile.mkdtemp(prefix="fusion_session_"))
    path = tmp / "session.json"

    q = PlayQueue()
    q.set_tracks(make_tracks(3), 1)
    q.mode = PlayMode.SHUFFLE
    assert play_session.save(q, 42_000, path=path) is True
    assert path.exists()

    again = play_session.load(path=path)
    assert again is not None
    assert [t.name for t in again.tracks] == ["T0", "T1", "T2"]
    assert again.index == 1
    assert again.mode == PlayMode.SHUFFLE
    assert again.position_ms == 42_000
    assert again.saved_at > 0

    # 快照能直接喂回队列（PlayerEngine.restoreSession 就是这么用的）
    q2 = PlayQueue()
    q2.load_dict(again.queue_dict())
    assert q2.size == 3 and q2.index == 1
    assert q2.current().name == "T1"
    assert q2.mode == PlayMode.SHUFFLE


def test_session_survives_junk():
    """会话文件是纯文本，手改坏了只能变成「没有会话」，不能把界面带崩。"""
    from app.core import session as play_session

    tmp = Path(tempfile.mkdtemp(prefix="fusion_session_"))
    path = tmp / "session.json"

    assert play_session.load(path=path) is None            # 文件根本不存在

    path.write_text("{ 这不是 json", encoding="utf-8")
    assert play_session.load(path=path) is None
    assert not path.exists()                               # 已备份成 .corrupt

    # 没有歌名 / 没有 id / 不是字典的条目一律丢掉；下标越界要夹回范围
    path.write_text(
        json.dumps(
            {
                "version": play_session.SCHEMA_VERSION,
                "position_ms": -5,
                "queue": {
                    "mode": "不认识的名字",
                    "index": 99,
                    "tracks": [
                        {"source": "wy", "songmid": "1", "name": "好歌"},
                        {"source": "wy", "songmid": "", "name": "没 id"},
                        {"source": "wy", "songmid": "2", "name": ""},
                        "根本不是字典",
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sess = play_session.load(path=path)
    assert sess is not None
    assert [t.name for t in sess.tracks] == ["好歌"]
    assert sess.index == 0                                 # 夹回唯一那首
    assert sess.position_ms == 0                           # 负数抹平
    assert sess.mode == PlayMode.LOOP_LIST                 # 不认识的名字回落

    # 本地曲目没有 songmid，靠路径站着；空壳条目才该被丢
    path.write_text(
        json.dumps(
            {
                "version": play_session.SCHEMA_VERSION,
                "queue": {"tracks": [{"source": "local", "name": "本地歌", "path": "D:/a.mp3"}]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sess = play_session.load(path=path)
    assert sess is not None and sess.tracks[0].is_local

    # 版本不认识：宁可当作没有会话，也不拿半个队列去猜
    path.write_text(
        json.dumps({"version": 999, "queue": {"tracks": [{"name": "A", "songmid": "1"}]}}),
        encoding="utf-8",
    )
    assert play_session.load(path=path) is None


def test_session_cleared_with_empty_queue():
    """清空队列后退出，不能把上一次的队列又捞回来。"""
    from app.core import session as play_session

    tmp = Path(tempfile.mkdtemp(prefix="fusion_session_"))
    path = tmp / "session.json"

    q = PlayQueue()
    q.set_tracks(make_tracks(2), 0)
    assert play_session.save(q, 8000, path=path) is True
    assert path.exists()

    q.clear()
    assert play_session.save(q, 0, path=path) is True
    assert not path.exists()
    assert play_session.load(path=path) is None


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


def test_vip_level_suffix():
    """等级显示成「黑胶SVIP·肆」，不是「黑胶SVIP Lv4」。"""
    from app.core.account import vip_level_suffix

    assert vip_level_suffix(4) == "·肆"
    assert vip_level_suffix(1) == "·壹"
    assert vip_level_suffix(9) == "·玖"
    assert vip_level_suffix(10) == "·拾"          # 十不写「壹拾」
    assert vip_level_suffix(11) == "·拾壹"
    assert vip_level_suffix(20) == "·贰拾"
    assert vip_level_suffix(35) == "·叁拾伍"
    assert vip_level_suffix(99) == "·玖拾玖"
    assert vip_level_suffix("4") == "·肆"          # 服务端偶尔给字符串

    # 没等级就不显示后缀（0 与各种脏值都算）
    assert vip_level_suffix(0) == ""
    assert vip_level_suffix(None) == ""
    assert vip_level_suffix("") == ""
    assert vip_level_suffix("bad") == ""
    assert vip_level_suffix(-3) == ""

    # 超出中文数字范围：等级是服务端给的，不猜，原样退回阿拉伯数字
    assert vip_level_suffix(100) == "·100"


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


# ──────────────────────────────────────────────────────────────
# 窗口尺寸 / 本地音乐的在线匹配
# ──────────────────────────────────────────────────────────────


def test_window_size_fits_screen():
    """窗口尺寸：够大就用想要的，屏幕小就让位，屏幕比下限还小则下限让位。

    1366×768 上任务栏一占可用高度只剩 728，760 的窗口会把底部播放栏顶出屏幕；
    1366×768 开 125% 缩放更极端（可用区域 1093×582，比窗口的最小高度还矮）。
    """
    from app.bridges.app import (
        SCREEN_MARGIN,
        WINDOW_DEFAULT_H,
        WINDOW_DEFAULT_W,
        WINDOW_FLOOR_H,
        WINDOW_FLOOR_W,
        fit_window,
    )

    # 屏幕够大：想要多大就多大
    assert fit_window(1180, 1920, 880) == 1180
    assert fit_window(760, 1040, 560) == 760
    # 屏幕装不下：夹到「可用区域 − 边距」
    assert fit_window(760, 728, 560) == 728 - SCREEN_MARGIN
    assert fit_window(1180, 1093, 880) == 1093 - SCREEN_MARGIN
    # 比下限还小：抬到下限（用户手动拖小了也不能小于它）
    assert fit_window(600, 1920, 880) == 880
    # 屏幕比下限还小：下限让位给屏幕，否则窗口自己就被撑出屏幕
    assert fit_window(560, 480, 560) == 480 - SCREEN_MARGIN
    assert fit_window(1180, 300, 880) == 300 - SCREEN_MARGIN
    # 拿不到屏幕信息（无显示器 / 远程会话）：只保证不小于下限
    assert fit_window(1180, 0, 880) == 1180
    assert fit_window(600, 0, 880) == 880
    # 脏数据不能把窗口搞成 0，也不能抛异常
    assert fit_window("bad", 1920, 880) == WINDOW_DEFAULT_W
    assert fit_window(1180, -5, 880) == 1180
    assert fit_window(10, 10, 880) >= 1

    assert WINDOW_DEFAULT_W > WINDOW_FLOOR_W
    assert WINDOW_DEFAULT_H > WINDOW_FLOOR_H


def test_close_decision():
    """关闭主窗口：有托盘才谈得上「收进托盘」，没有就一律退出。

    这里守的是最要命的一种错法：托盘用不了还把窗口藏起来 —— 用户点了 ✕，
    窗口消失了，进程还在放歌，任务栏里却什么都没有，再也找不回来。
    """
    from app.bridges.app import CLOSE_ACTIONS, close_decision
    from app.config import DEFAULTS

    assert CLOSE_ACTIONS == ("ask", "tray", "quit")
    # 默认「每次询问」，而且托盘图标默认开着
    assert DEFAULTS["window"]["close_action"] == "ask"
    assert DEFAULTS["window"]["tray_icon"] is True

    # 有托盘：照设置走
    assert close_decision("ask", True) == "ask"
    assert close_decision("tray", True) == "tray"
    assert close_decision("quit", True) == "quit"
    # 大小写与空白不该改变结论
    assert close_decision(" TRAY ", True) == "tray"
    assert close_decision("Quit", True) == "quit"
    # 设置里是脏值 / 空值：回到最保守的「每次询问」，而不是猜
    assert close_decision("", True) == "ask"
    assert close_decision(None, True) == "ask"
    assert close_decision("bogus", True) == "ask"

    # 没有托盘（系统不支持，或用户把托盘图标关了）：一律直接退出
    for action in CLOSE_ACTIONS + ("bogus", "", None):
        assert close_decision(action, False) == "quit"


def test_local_match_rules():
    """本地曲目的在线匹配：什么时候去搜、匹配到之后写什么、什么时候沿用上次的。"""
    from app.core import localmatch
    from app.sources.base import MusicInfo

    def local(name, path, *, cover="", interval=200, matched=False):
        track = Track(source="local", songmid=path, name=name, singer="歌手",
                      interval=interval, path=path, cover=cover)
        if matched:
            track.match_source, track.match_songmid = "wy", "42"
        return track

    # 缺封面 → 必须匹配
    assert localmatch.needs_match(local("歌", "x.mp3")) is True
    # 有内嵌封面 + 有同目录 .lrc → 什么都不缺，不必联网
    assert localmatch.needs_match(local("歌", "x.mp3", cover="file:///c.jpg"),
                                  has_lyric=True) is False
    # 有内嵌封面但没有歌词 → 还得匹配一次（歌词要用在线身份）
    assert localmatch.needs_match(local("歌", "x.mp3", cover="file:///c.jpg"),
                                  has_lyric=False) is True
    # 已经匹配过了 → 不再重复搜
    assert localmatch.needs_match(local("歌", "x.mp3", cover="file:///c.jpg",
                                        matched=True), has_lyric=False) is False
    # 连歌名都没有的没法搜
    assert localmatch.needs_match(Track(source="local", path="x.mp3")) is False
    assert localmatch.needs_match(None) is False

    # 匹配结果：记身份 + 补封面
    track = local("歌", "x.mp3")
    info = MusicInfo(name="歌", singer="歌手", source="wy", songmid="42",
                     album_name="专辑", img="http://cover/1.jpg", interval=200)
    assert localmatch.apply_match(track, info) is True
    assert (track.match_source, track.match_songmid) == ("wy", "42")
    assert track.cover == "http://cover/1.jpg"

    # 内嵌封面比在线封面准：只补不覆盖
    track = local("歌", "x.mp3", cover="file:///inner.jpg")
    assert localmatch.apply_match(track, info) is True
    assert track.cover == "file:///inner.jpg"
    # 没有 id 的匹配结果一律不认
    assert localmatch.apply_match(local("歌", "x.mp3"), None) is False
    assert localmatch.apply_match(
        local("歌", "x.mp3"), MusicInfo(name="歌", singer="", source="wy", songmid="")
    ) is False

    # 重扫沿用：只有时长一致才认
    old = local("歌", "x.mp3", interval=200, matched=True)
    old.cover = "http://cover/1.jpg"
    table = localmatch.reuse_matches([old, local("没匹配过", "y.mp3")])
    assert list(table) == [localmatch.key_for_path("x.mp3")]

    fresh = local("歌", "x.mp3", interval=200)
    assert localmatch.adopt_match(fresh, old) is True
    assert (fresh.match_source, fresh.match_songmid) == ("wy", "42")
    assert fresh.cover == "http://cover/1.jpg"
    # 文件被换成别的歌（时长变了）→ 不认，重新匹配
    assert localmatch.adopt_match(local("歌", "x.mp3", interval=260), old) is False
    # 时长读不出来 → 没有依据，也不认
    assert localmatch.adopt_match(local("歌", "x.mp3", interval=0), old) is False
    # 新读出来的内嵌封面不会被上次的在线封面顶掉
    fresh = local("歌", "x.mp3", interval=200, cover="file:///inner.jpg")
    assert localmatch.adopt_match(fresh, old) is True
    assert fresh.cover == "file:///inner.jpg"
    assert localmatch.adopt_match(None, old) is False
    assert localmatch.adopt_match(local("歌", "x.mp3"), None) is False

    assert localmatch.matched_count([old, fresh]) == 2
    assert localmatch.matched_count([]) == 0
    assert [t.name for t in localmatch.pending_matches([old, local("缺封面", "z.mp3")])] \
        == ["缺封面"]


def test_read_embedded_cover():
    """内嵌封面：MP3 的 ID3 APIC 读得出来，没有封面时返回空（交给在线匹配）。

    顺手把「读出来就写进封面缓存」这条链路走一遍 —— 封面来自本地文件的标签，
    QML 自己解析不了，必须先在扫描时落成文件。
    """
    import os
    import tempfile
    from pathlib import Path

    from PySide6.QtCore import QUrl

    from app.core.resolver import read_picture, resolve_local_metadata

    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000a49444154789c6360000002000100ffff0300000600"
        "05570c1f0000000049454e44ae426082"
    )
    tmp = Path(tempfile.mkdtemp(prefix="fusion_cover_"))

    def write_mp3(path, *, with_cover):
        from mutagen.id3 import APIC, ID3, TALB, TPE1, TIT2

        header = b"\xff\xfb\x90\x00"
        path.write_bytes((header + b"\x00" * (417 - len(header))) * 40)
        tags = ID3()
        tags.add(TIT2(encoding=3, text="测试歌曲"))
        tags.add(TPE1(encoding=3, text="测试歌手"))
        tags.add(TALB(encoding=3, text="测试专辑"))
        if with_cover:
            tags.add(APIC(encoding=3, mime="image/png", type=3, desc="Cover", data=png))
        tags.save(str(path))

    with_cover = tmp / "with.mp3"
    without = tmp / "without.mp3"
    write_mp3(with_cover, with_cover=True)
    write_mp3(without, with_cover=False)

    assert read_picture(str(with_cover)) == (png, "image/png")
    assert read_picture(str(without)) == (b"", "")

    # 封面缓存落在数据目录里，测试期间临时指到 tmp
    previous = os.environ.get("FUSION_MUSIC_HOME")
    os.environ["FUSION_MUSIC_HOME"] = str(tmp / "data")
    try:
        track = resolve_local_metadata(str(with_cover))
        assert track.name == "测试歌曲" and track.singer == "测试歌手"
        assert track.cover.startswith("file://")
        cached = Path(QUrl(track.cover).toLocalFile())
        assert cached.exists() and cached.read_bytes() == png
        # 没有内嵌封面的留空，由在线匹配去补
        assert resolve_local_metadata(str(without)).cover == ""
    finally:
        if previous is None:
            os.environ.pop("FUSION_MUSIC_HOME", None)
        else:
            os.environ["FUSION_MUSIC_HOME"] = previous


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


# ──────────────────────────────────────────────────────────────
# 音量均衡：响度测算（EBU R128 / BS.1770-4）
# ──────────────────────────────────────────────────────────────


def _sine(amplitude: float, freq: float = 1000.0, seconds: float = 5.0, rate: int = 8000):
    import math

    return [amplitude * math.sin(2 * math.pi * freq * i / rate)
            for i in range(int(seconds * rate))]


def test_loudness_filters_match_bs1770():
    """48 kHz 的 K 加权系数必须与 BS.1770-4 附录给的值一致。

    这张系数表是整个功能的地基：算错了不会崩，只会让「均衡」变成
    「所有歌都朝同一个方向偏」。标准值与自研公式对得上，才敢在其它采样率
    上用同一套模拟原型去现算。
    """
    from app.core import loudness as L

    rlb, shelf = L.k_weighting_coeffs(48000)
    reference_shelf = (1.53512485958697, -2.69169618940638, 1.19839281085285,
                       -1.69065929318241, 0.73248077421585)
    reference_rlb = (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)
    for mine, want in ((shelf, reference_shelf), (rlb, reference_rlb)):
        for got, expected in zip(mine, want):
            assert abs(got - expected) < 2e-6, (got, expected)

    # 高通级：b 恒为 [1, -2, 1]（整份实现的口径，改了就不是 BS.1770 了）
    assert abs(rlb[0] - 1.0) < 1e-9 and abs(rlb[1] + 2.0) < 1e-9

    # 8 kHz 上同样设计得出来（解码器给的就是这个采样率）
    rlb8, shelf8 = L.k_weighting_coeffs(8000)
    assert all(abs(c) < 10 for c in rlb8 + shelf8)


def test_loudness_known_signals():
    """已知信号的积分响度必须落在标准口径上。

    立体声正弦（每声道幅度 A）的响度 ≈ 20lg(A) + 10lg(2) - 0.691 + K加权，
    1 kHz 附近 K 加权约 0 dB，所以 -20 dBFS 的立体声正弦约为 -20 LUFS。
    """
    from app.core import loudness as L

    mono = _sine(0.1)
    stereo = L.analyze([mono, mono], 8000)
    assert abs(stereo.loudness_lufs - (-19.99)) < 0.25, stereo.loudness_lufs

    # 单声道同一信号比立体声低 3.01 dB —— 这正是「先混单再算」那个坑
    single = L.analyze(mono, 8000)
    assert abs((stereo.loudness_lufs - single.loudness_lufs) - 3.0103) < 0.05, (
        stereo.loudness_lufs, single.loudness_lufs)


def test_loudness_gating_uses_energy_domain():
    """相对门限必须在**能量域**取平均（BS.1770-4 式 5/6）。

    先响 4 秒、再轻 20 dB 响 8 秒：把各块的 dB 值直接算术平均的话，门限会掉到
    -43 dB，轻的那段也被算进去（约 -24.7 LUFS）；按标准（各块均方先平均）
    门限是 -30 dB 出头，轻的那段被挡掉，结果是 -20.2 LUFS。差 4.5 LU，
    听感上就是「安静段落把整首歌的增益带偏」。
    """
    from app.core import loudness as L

    rate = 8000
    loud = _sine(0.1, seconds=4.0, rate=rate)
    quiet = _sine(0.01, seconds=8.0, rate=rate)
    mixed = loud + quiet
    result = L.analyze([mixed, mixed], rate)
    assert abs(result.loudness_lufs - (-20.16)) < 0.35, result.loudness_lufs
    assert result.blocks > result.gated_blocks      # 轻的那段确实被门限挡掉了


def test_loudness_handles_degenerate_input():
    """静音 / 空 / 太短 / NaN 都不能算出「一个看起来正常的增益」。"""
    from app.core import loudness as L

    assert L.analyze([], 8000).loudness_lufs is None
    assert L.analyze([0.0] * 40000, 8000).loudness_lufs is None      # 静音
    assert L.analyze([0.5] * 100, 8000).loudness_lufs is None        # 太短（<100ms）

    # 200 ms 的短促信号仍应测得出来（铃声、试听片段的兜底路径）。
    # 这一段守的是分块兜底里的一个真 bug：200 ms 正好凑满两个 100 ms 段，
    # 零头是空的 —— 只统计「没满一段的那部分」会把整段已经收尾的能量漏掉，
    # 于是一个响亮的短音被算成「一个样本都没有」。
    short = L.analyze(_sine(0.3, seconds=0.2), 8000)
    assert short.loudness_lufs is not None and short.measurable
    assert short.loudness_lufs < 0, short.loudness_lufs
    # 50 ms（不足 MIN_BLOCK_SECONDS）仍然判成测不出来
    assert L.analyze(_sine(0.3, seconds=0.05), 8000).loudness_lufs is None

    # NaN / inf 就地归零：峰值被忽略，响度不受污染
    dirty = L.analyze([float("nan"), float("inf")] + _sine(0.2), 8000)
    assert dirty.loudness_lufs is not None
    assert abs(dirty.peak - 0.2) < 0.02, dirty.peak


def test_loudness_streaming_matches_batch():
    """分块喂样本（解码器就是一块一块给的）与一次性分析必须一致。"""
    from app.core import loudness as L

    signal = _sine(0.25, seconds=3.0)
    whole = L.analyze([signal, signal], 8000)

    meter = L.LoudnessMeter(8000, channels=2)
    chunk = 997          # 故意不是 100ms 的整数倍，考验分块对齐
    for start in range(0, len(signal), chunk):
        piece = signal[start:start + chunk]
        meter.feed([piece, piece])
    streamed = meter.result()

    assert abs(streamed.loudness_lufs - whole.loudness_lufs) < 0.01, (
        streamed.loudness_lufs, whole.loudness_lufs)
    assert abs(streamed.peak - whole.peak) < 1e-9


def test_gain_db_rules():
    """增益的三道约束：目标响度、防削波、上下限。"""
    import math

    from app.core import loudness as L

    # 目标响度：-10 LUFS 的曲子、目标 -14 → -4 dB
    assert abs(L.gain_db(-10.0, 1.0, peak_ceiling=2.0) - (-4.0)) < 1e-6
    # 防削波优先：峰值 0.9 时最多只能加 20lg(0.891/0.9)（是个负数）
    limited = L.gain_db(-30.0, 0.9)
    assert abs(limited - 20 * math.log10(0.891 / 0.9)) < 1e-6
    # 偏轻的曲子允许抬升
    assert abs(L.gain_db(-22.0, 0.3) - 8.0) < 1e-6
    # 不允许抬升时最多到 0 dB
    assert L.gain_db(-22.0, 0.3, allow_boost=False) == 0.0
    # 上下限夹紧
    assert L.gain_db(-60.0, 0.05) == L.DEFAULT_MAX_GAIN_DB
    assert L.gain_db(10.0, 1.0) == L.DEFAULT_MIN_GAIN_DB
    # 未知响度 / 未知峰值：一律不处理，绝不瞎猜
    assert L.gain_db(None, 0.5) == 0.0
    assert L.gain_db(-20.0, 0.0) == 0.0
    # dB ↔ 倍数
    assert abs(L.db_to_ratio(-6.0206) - 0.5) < 1e-4
    assert abs(L.ratio_to_db(0.5) - (-6.0206)) < 1e-4
    assert L.describe_gain(0.0) == "不调整"
    assert "dB" in L.describe_gain(-3.5)


# ──────────────────────────────────────────────────────────────
# 音量均衡：测量缓存
# ──────────────────────────────────────────────────────────────


def test_loudness_store_roundtrip_and_ttl():
    """缓存要能落盘读回，失败条目要有重试窗口，音源兜底要够样本才给值。"""
    import time

    from app.core import loudness_store as S

    tmp = Path(tempfile.mkdtemp(prefix="fusion_loudness_"))
    store = S.LoudnessStore(tmp / "loudness.json")

    store.put(S.Measurement(uid="wy:1", loudness_lufs=-10.0, peak=1.0, seconds=180.0,
                            partial=False, source="wy", method=S.METHOD_DECODE, ok=True))
    assert store.save(force=True) is True

    loaded = S.LoudnessStore(tmp / "loudness.json").get("wy:1")
    assert loaded is not None and abs(loaded.loudness_lufs + 10.0) < 1e-9
    assert loaded.partial is False and loaded.source == "wy"

    # 版本不符 → 整份作废（算法换了口径必须重算）
    (tmp / "loudness.json").write_text(
        json.dumps({"version": S.CACHE_VERSION - 1, "entries": {"wy:1": {}}}),
        encoding="utf-8")
    assert S.LoudnessStore(tmp / "loudness.json").size == 0

    # 失败条目：未过期时视为「已有结论」（不反复重试），过期后当作没有
    store = S.LoudnessStore(tmp / "loudness2.json")
    store.put(S.Measurement.failure("wy:2", source="wy"))
    assert store.get("wy:2") is not None
    store.put(S.Measurement(uid="wy:3", loudness_lufs=None, peak=0.0, ok=False,
                            source="wy", at=time.time() - S.FAILURE_TTL_SECONDS - 10))
    assert store.get("wy:3") is None
    assert store.get("wy:3", retry_failed=False) is not None

    # 音源兜底：样本不足不给值，够了给中位数并夹紧
    for i in range(4):
        store.put(S.Measurement(uid=f"kw:{i}", loudness_lufs=-20.0, peak=0.2,
                                partial=False, source="kw", ok=True))
    assert store.source_offset_db("kw") == 0.0            # 只有 4 个样本
    for i in range(4, 11):
        store.put(S.Measurement(uid=f"kw:{i}", loudness_lufs=-20.0, peak=0.2,
                                partial=False, source="kw", ok=True))
    offset = store.source_offset_db("kw")
    assert 0 < offset <= S.SOURCE_OFFSET_LIMIT_DB, offset
    assert store.source_offset_db("") == 0.0

    stats = store.stats()
    assert stats["measured"] >= 11 and stats["failed"] >= 1
    assert S.parse_replaygain_tag("-7.25 dB") == -7.25
    assert S.parse_replaygain_tag("") is None
    assert S.parse_replaygain_tag("不是数字") is None
    assert store.clear() > 0 and store.size == 0


def test_gain_db_for_uses_stricter_ceiling_when_partial():
    """只分析了前一段时（流媒体）峰值上限要更保守。"""
    from app.core import loudness as L
    from app.core import loudness_store as S

    full = S.Measurement(uid="a", loudness_lufs=-20.0, peak=0.95, partial=False, ok=True)
    part = S.Measurement(uid="b", loudness_lufs=-20.0, peak=0.95, partial=True, ok=True)
    full_gain, part_gain = S.gain_db_for(full), S.gain_db_for(part)
    assert full_gain > part_gain, (full_gain, part_gain)
    assert abs(full_gain - L.gain_db(-20.0, 0.95, peak_ceiling=L.DEFAULT_PEAK_CEILING)) < 1e-9
    assert abs(part_gain - L.gain_db(-20.0, 0.95, peak_ceiling=L.PARTIAL_PEAK_CEILING)) < 1e-9
    # 没有测量值 / 测量失败 → 0 dB
    assert S.gain_db_for(None) == 0.0
    assert S.gain_db_for(S.Measurement.failure("c")) == 0.0


# ──────────────────────────────────────────────────────────────
# 自动更新：版本、资产、摘要
# ──────────────────────────────────────────────────────────────


def _release_payload(tag="v1.1.0", assets=None, prerelease=False):
    return {
        "tag_name": tag,
        "name": tag,
        "body": "## 说明\n\n| 平台 | 文件 |\n|--|--|\n| win | a.zip |\n\n正文",
        "html_url": f"https://github.com/Janson20/FusionMusicPlayer/releases/tag/{tag}",
        "published_at": "2026-01-02T03:04:05Z",
        "prerelease": prerelease,
        "assets": assets if assets is not None else [
            {"name": "FusionMusicPlayer-1.1.0-win-x64.zip",
             "browser_download_url": "https://github.com/x/releases/download/v1.1.0/a.zip",
             "size": 1024, "digest": "sha256:" + "a" * 64},
            {"name": "FusionMusicPlayer-1.1.0-win-x64.exe",
             "browser_download_url": "https://github.com/x/releases/download/v1.1.0/a.exe",
             "size": 2048, "digest": "sha256:" + "b" * 64},
        ],
    }


def test_version_parse_and_compare():
    """版本号解析与比较：预发布永远小于同号正式版。"""
    from app.core import updater as U

    assert U.parse_version("v1.2.3") == (1, 2, 3, "")
    assert U.parse_version("1.2.3-beta.1") == (1, 2, 3, "beta.1")
    assert U.parse_version("0.0.0-dev") == (0, 0, 0, "dev")
    assert U.parse_version("不是版本号") is None
    assert U.parse_version("") is None

    assert U.is_newer("1.0.7", "1.0.6") is True
    assert U.is_newer("1.1.0", "1.0.6") is True
    assert U.is_newer("1.0.6", "1.0.6") is False
    assert U.is_newer("1.0.5", "1.0.6") is False
    assert U.is_newer("1.2.0", "1.2.0-rc1") is True     # 正式版 > 预发布
    assert U.is_newer("1.2.0-rc1", "1.2.0") is False
    assert U.compare_versions("1.0.6", "dev") is None
    # 解析不了时一律「不更新」，绝不因为看不懂就去下载
    assert U.is_newer("最新版", "1.0.6") is False
    assert U.is_newer("1.0.7", "dev") is False


def test_pick_asset_by_install_kind():
    """按发行形态选资产：便携版要 zip，单文件版要 exe。"""
    from app.core import updater as U

    release = U.parse_release(_release_payload())
    assert release is not None and release.version == "1.1.0"
    assert release.prerelease is False and len(release.assets) == 2

    assert release.asset_for(U.KIND_ONEDIR).name.endswith(".zip")
    assert release.asset_for(U.KIND_ONEFILE).name.endswith(".exe")
    # 源码运行不给资产（界面会引导去发布页）
    assert release.asset_for(U.KIND_SOURCE) is None

    # 命名对不上时按后缀退让，而不是随便挑一个
    odd = U.parse_release(_release_payload(tag="v2.0.0", assets=[
        {"name": "something-win-x64.zip", "browser_download_url": "https://github.com/a.zip",
         "size": 1, "digest": "sha256:" + "c" * 64},
    ]))
    assert odd.asset_for(U.KIND_ONEDIR).name == "something-win-x64.zip"
    assert odd.asset_for(U.KIND_ONEFILE) is None
    assert U.pick_asset([], U.KIND_ONEDIR) is None


def test_parse_release_rejects_foreign_assets_and_bad_tags():
    """只接受 GitHub 自己的 https 地址；版本号解析不出来就当没有这次发布。"""
    from app.core import updater as U

    assert U.parse_release({"tag_name": "nightly"}) is None
    assert U.parse_release({}) is None
    assert U.parse_release(_release_payload(tag="不是版本")) is None
    assert U.parse_release("不是字典") is None

    mixed = U.parse_release(_release_payload(assets=[
        {"name": "evil.exe", "browser_download_url": "http://evil.example.com/x.exe",
         "size": 1, "digest": "sha256:" + "d" * 64},
        {"name": "http.exe", "browser_download_url": "http://github.com/x.exe",
         "size": 1, "digest": "sha256:" + "d" * 64},
        {"name": "ok.exe", "browser_download_url": "https://github.com/x.exe",
         "size": 1, "digest": "sha256:" + "d" * 64},
    ]))
    assert [a.name for a in mixed.assets] == ["ok.exe"]

    assert U.url_allowed("https://github.com/a") is True
    assert U.url_allowed("https://objects.githubusercontent.com/a") is True
    assert U.url_allowed("https://github.com.evil.com/a") is False
    assert U.url_allowed("http://github.com/a") is False
    assert U.url_allowed("file:///etc/passwd") is False
    assert U.url_allowed("") is False


def test_digest_verification():
    """下载完必须对上服务端给的 sha256；格式不对一律不认。"""
    import hashlib

    from app.core import updater as U

    tmp = Path(tempfile.mkdtemp(prefix="fusion_upd_"))
    target = tmp / "package.zip"
    target.write_bytes(b"hello update")
    good = "sha256:" + hashlib.sha256(b"hello update").hexdigest()

    assert U.digest_matches(target, good) is True
    assert U.digest_matches(target, "sha256:" + "0" * 64) is False
    assert U.digest_matches(target, "") is False
    assert U.digest_matches(target, "md5:abc") is False
    assert U.sha256_file(target) == hashlib.sha256(b"hello update").hexdigest()

    asset = U.ReleaseAsset(name="a.zip", url="https://github.com/a.zip", digest=good)
    assert asset.sha256 == good.split(":")[1]
    assert U.ReleaseAsset(name="a", url="", digest="").sha256 == ""
    assert U.ReleaseAsset(name="a", url="", size=0).size_text == "未知大小"


def test_install_kind_detection():
    """发行形态判定：源码 / 便携版（_internal 同级）/ 单文件（_MEIxxxx 临时目录）。"""
    import sys as _sys

    from app.core import updater as U

    saved = (getattr(_sys, "frozen", None), getattr(_sys, "_MEIPASS", None), _sys.executable)
    try:
        _sys.frozen = False                              # type: ignore[attr-defined]
        assert U.install_kind() == U.KIND_SOURCE

        exe = Path(tempfile.mkdtemp(prefix="fusion_kind_")) / "FusionMusicPlayer.exe"
        exe.write_bytes(b"")
        _sys.executable = str(exe)
        _sys.frozen = True                               # type: ignore[attr-defined]
        _sys._MEIPASS = str(exe.parent / "_internal")    # type: ignore[attr-defined]
        assert U.install_kind() == U.KIND_ONEDIR

        _sys._MEIPASS = str(Path(tempfile.gettempdir()) / "_MEI123456")  # type: ignore[attr-defined]
        assert U.install_kind() == U.KIND_ONEFILE

        # 没有 _MEIPASS 但已冻结：按目录版处理（替换方式一样）
        del _sys._MEIPASS
        assert U.install_kind() == U.KIND_ONEDIR
    finally:
        _sys.executable = saved[2]
        for name, value in (("frozen", saved[0]), ("_MEIPASS", saved[1])):
            if value is None:
                try:
                    delattr(_sys, name)
                except AttributeError:
                    pass
            else:
                setattr(_sys, name, value)


def test_release_notes_excerpt_and_size():
    """更新说明要能直接塞进界面：去掉下载表格、截断超长内容。"""
    from app.core import updater as U

    text = U.release_notes_excerpt(_release_payload()["body"])
    assert "## 说明" in text and "正文" in text
    assert "|" not in text and "a.zip" not in text

    excerpt = U.release_notes_excerpt("\n".join(f"第 {i} 行" for i in range(500)), limit=100)
    assert len(excerpt) <= 101 and excerpt.endswith("…")
    assert U.release_notes_excerpt("") == ""

    assert U.human_size(0) == "未知大小"
    assert U.human_size(512) == "512 B"
    assert U.human_size(2048) == "2.0 KB"
    assert U.human_size(96 * 1024 * 1024) == "96.0 MB"


# ──────────────────────────────────────────────────────────────
# 打包后的资源路径（托盘 / 任务栏图标）
# ──────────────────────────────────────────────────────────────


def test_resource_dir_follows_pyinstaller_layout():
    """打包后 ``assets/`` 不在 exe 旁边，而在 ``_internal/`` 或 ``_MEIxxxx`` 里。

    守的是「打包成 exe 之后最小化到托盘没有图标」这个真机故障：
    PyInstaller 6 的 onedir 把数据文件（含 ``assets/``）放进 ``_internal/``，
    onefile 放进 ``%TEMP%\\_MEIxxxx`` —— 按 ``program_dir() / "assets"`` 去找，
    两种打包形态都找不到图标文件，界面照常启动、托盘上却是一个空白位。
    实测过：``dist/FusionMusicPlayer/`` 下只有 exe 与 ``_internal/``。
    """
    import sys as _sys

    from app import paths

    saved = (getattr(_sys, "frozen", None), getattr(_sys, "_MEIPASS", None), _sys.executable)
    root = Path(tempfile.mkdtemp(prefix="fusion_layout_"))
    try:
        # 开发态：资源就在项目根目录
        _sys.frozen = False                              # type: ignore[attr-defined]
        assert paths.resource_dir() == paths.program_dir()

        # onedir：exe 在 <app>/，资源在 <app>/_internal/
        exe_dir = root / "app"
        bundle = exe_dir / "_internal"
        (bundle / "assets").mkdir(parents=True)
        (bundle / "assets" / "icon.ico").write_bytes(b"ico")
        exe = exe_dir / "FusionMusicPlayer.exe"
        exe.write_bytes(b"MZ")

        _sys.frozen = True                               # type: ignore[attr-defined]
        _sys.executable = str(exe)
        _sys._MEIPASS = str(bundle)                      # type: ignore[attr-defined]
        # 比 resolve() 之后的路径：Windows 上临时目录常拿到 8.3 短名
        # （C:\Users\ADMINI~1\...），而 program_dir() 内部会 resolve 成长名
        assert paths.program_dir() == exe_dir.resolve(), "用户数据仍然要挨着 exe 放"
        assert paths.resource_dir() == bundle
        assert (paths.resource_dir() / "assets" / "icon.ico").exists()
        assert not (paths.program_dir() / "assets").exists(), "这正是以前的写法找不到图标的原因"

        # onefile：资源在 %TEMP%\_MEIxxxx
        _sys._MEIPASS = str(root / "_MEI123456")         # type: ignore[attr-defined]
        assert paths.resource_dir() == root / "_MEI123456"

        # 没有 _MEIPASS 的极端情况：退回 exe 目录，别抛异常
        del _sys._MEIPASS
        assert paths.resource_dir() == exe_dir.resolve()
    finally:
        _sys.executable = saved[2]
        for name, value in (("frozen", saved[0]), ("_MEIPASS", saved[1])):
            if value is None:
                try:
                    delattr(_sys, name)
                except AttributeError:
                    pass
            else:
                setattr(_sys, name, value)


def test_tray_icon_source_uses_bundled_assets():
    """托盘图标的地址必须指向打包进程序的那份 ``assets/icon.ico``。

    这里不启动界面，只把 ``AppController.trayIconSource`` 这条取值链走通：
    它以前用 ``program_dir()``，打包后拿到空串 —— 托盘图标就是空的。
    """
    import sys as _sys

    from app import paths
    from app.bridges.app import AppController

    saved = (getattr(_sys, "frozen", None), getattr(_sys, "_MEIPASS", None), _sys.executable)
    root = Path(tempfile.mkdtemp(prefix="fusion_tray_"))

    class _Config:
        def get(self, key, default=None):
            return default

    try:
        exe_dir = root / "app"
        bundle = exe_dir / "_internal"
        (bundle / "assets").mkdir(parents=True)
        icon = bundle / "assets" / "icon.ico"
        icon.write_bytes(b"\x00\x00\x01\x00")            # 内容无所谓，只看能不能定位

        _sys.frozen = True                               # type: ignore[attr-defined]
        _sys.executable = str(exe_dir / "FusionMusicPlayer.exe")
        _sys._MEIPASS = str(bundle)                      # type: ignore[attr-defined]

        controller = AppController(_Config())
        source = controller.trayIconSource
        assert source.startswith("file:"), source
        assert "icon.ico" in source, source
        assert "_internal" in source or "_MEI" in source, source

        # 图标文件真的不在 exe 旁边时，也必须是「找得到打包里的那份」
        assert not (paths.program_dir() / "assets" / "icon.ico").exists()
    finally:
        _sys.executable = saved[2]
        for name, value in (("frozen", saved[0]), ("_MEIPASS", saved[1])):
            if value is None:
                try:
                    delattr(_sys, name)
                except AttributeError:
                    pass
            else:
                setattr(_sys, name, value)


# ──────────────────────────────────────────────────────────────
# 歌手过多时的折叠
# ──────────────────────────────────────────────────────────────


def test_artist_names_fold_when_too_many():
    """歌手多于阈值时只铺开前几位，其余折叠成「等 N 人」。

    守的是「歌手太多导致显示问题」这个真机故障：歌手行是逐个名字排的
    RowLayout，**不会换行**，十几个歌手（企划曲 / 周年纪念集很常见）会把这一行
    撑到窗口两边、横着盖住封面与歌词。

    ``ArtistNames.js`` 是 QML 里的库文件，这里用 Qt 自带的 JS 引擎（QJSEngine）
    把它的规则原样跑一遍 —— 不引 node 之类的额外工具，测的也确实是 QML 用的那个引擎。
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQml import QJSEngine

    # QJSEngine 需要一个 QCoreApplication，而且**必须把引用留住**：
    # 让它被 Python 回收掉的话，Qt 之后就在对着一个已销毁的实例干活
    # （实测直接崩，退出码 0xC0000409）
    global _QT_APP
    if _QT_APP is None:
        _QT_APP = QCoreApplication.instance() or QCoreApplication([])

    source = (Path(__file__).resolve().parent.parent
              / "app" / "ui" / "ArtistNames.js").read_text(encoding="utf-8")
    assert ".pragma library" in source
    # .pragma 只在 QML 的 import 里有效，直接 evaluate 要去掉
    engine = QJSEngine()
    engine.evaluate(source.replace(".pragma library", ""), "ArtistNames.js")

    many = ("原幻乐社(十八渡)、非凤FreakMalus、莫临Moris、伪证的火云龙、洛天依Official、"
            "言和、乐正绫、墨清弦、心华、星尘、海伊、赤羽、苍穹、诗岸、乐正龙牙、牧心、微羽摩柯")
    probe = engine.evaluate("""
        (function () {
            var many = "%s";
            function summarize(text, limit) {
                var parts = limit === undefined ? linkParts(text) : linkParts(text, limit);
                var names = [];
                var last = parts.length ? parts[parts.length - 1]
                                        : { text: "", more: false, total: 0 };
                for (var i = 0; i < parts.length; i++)
                    if (!parts[i].separator) names.push(parts[i].text);
                return { count: names.length, names: names, last: last.text,
                         more: last.more === true, total: last.total, parts: parts.length };
            }
            return { folded: summarize(many), unlimited: summarize(many, 0),
                     few: summarize("A、B"), single: summarize("仅一位"),
                     empty: summarize("") };
        })()
    """ % many)
    assert not probe.isError(), probe.toString()
    data = probe.toVariant()

    folded = data["folded"]
    # 前 3 位 + 一个「等 N 人」片段
    assert folded["count"] == 4, folded
    assert folded["names"][:3] == ["原幻乐社(十八渡)", "非凤FreakMalus", "莫临Moris"], folded
    assert folded["last"] == "等 17 人", folded
    assert folded["more"] is True and folded["total"] == 17
    # limit=0 表示不折叠（完整列表 / 菜单用）
    assert data["unlimited"]["count"] == 17 and data["unlimited"]["more"] is False
    # 人少的时候不该出现「等 N 人」，也不该多出分隔符
    assert data["few"]["count"] == 2 and data["few"]["more"] is False
    assert data["few"]["parts"] == 3          # A + 分隔符 + B
    assert data["single"]["count"] == 1 and data["single"]["parts"] == 1
    assert data["empty"]["count"] == 0


# ──────────────────────────────────────────────────────────────
# 自动更新：暂存与替换脚本
# ──────────────────────────────────────────────────────────────


def test_update_script_never_touches_user_data():
    """替换脚本必须：等旧进程退出、排除 data、失败回滚、按形态分支。"""
    from app.core import update_install as I

    script = I.build_script()
    assert "@@" not in script, "还有没替换掉的占位符"
    assert "'/XD', 'data'" in script, "备份与覆盖都必须排除 data 目录"
    assert "$DataDir" in script
    # 备份目录本身也在 data/updates 里：不排除它的话 robocopy 会自己喂自己
    assert "Invoke-Robocopy $InstallDir $BackupDir @('/XD', 'data', $DataDir, $BackupDir, $StagingDir)" in script
    assert "Get-Process -Id $AppPid" in script, "必须等旧进程退出（否则 exe 换不掉）"
    assert "robocopy" in script.lower()
    assert "Start-Process" in script
    assert "回滚" in script
    assert "$Mode -eq 'onefile'" in script and "Invoke-Robocopy $StagingDir $InstallDir" in script
    # 脚本自己不能躺在会被覆盖的位置
    assert "apply_update.ps1" == I.SCRIPT_NAME

    # 下面三条都是**真机跑脚本才暴露出来**的坑，别让它们被改回去：
    # 1) robocopy 默认跳过「大小与时间戳都一样」的文件，更新必须带 /IS 强制覆盖；
    assert "'/IS'" in script, "覆盖步骤必须带 /IS，否则同大小同时间的文件会被静默跳过"
    # 2) 只看 robocopy 退出码不够（目录/文件冲突时它会跳过而不报错），
    #    覆盖完必须逐文件核对；
    assert "Test-StagedTree" in script and "替换结果已校验" in script
    # 3) 坏包必须在**动任何文件之前**就被拒掉，而不是替换到一半再回滚。
    assert "放弃更新（程序文件未做任何改动）" in script
    # 4) 日志目录可能还不存在，Write-Log 要自己建（否则失败原因一个字都留不下）。
    assert "Split-Path -Parent $LogFile" in script


def test_stage_zip_rejects_path_traversal():
    """解压要防目录穿越，而且必须真的看到可执行文件才算暂存成功。"""
    import zipfile

    from app.core import update_install as I

    tmp = Path(tempfile.mkdtemp(prefix="fusion_stage_"))

    evil = tmp / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../escaped.txt", "bad")
        z.writestr("FusionMusicPlayer.exe", "MZ")
    staging = I.stage_release(evil, "onedir", tmp / "stage1")
    assert not (tmp / "escaped.txt").exists(), "目录穿越没被挡住"
    assert (staging / "FusionMusicPlayer.exe").exists()
    assert I.find_staged_exe(staging) is not None

    empty = tmp / "empty.zip"
    with zipfile.ZipFile(empty, "w") as z:
        z.writestr("readme.txt", "nothing here")
    try:
        I.stage_release(empty, "onedir", tmp / "stage2")
        raise AssertionError("没有 exe 的包不该被接受")
    except RuntimeError as e:
        assert "可执行文件" in str(e)

    # 单文件形态：资产本身就是 exe，原样搬到暂存目录
    exe = tmp / "FusionMusicPlayer-2.0.0-win-x64.exe"
    exe.write_bytes(b"MZ")
    staging = I.stage_release(exe, "onefile", tmp / "stage3")
    assert (staging / I.STAGED_EXE_NAME).exists()

    # 源码运行不支持暂存
    try:
        I.stage_release(exe, "source", tmp / "stage4")
        raise AssertionError("源码运行不该走暂存")
    except RuntimeError:
        pass


def test_can_auto_install_explains_itself():
    """不能自动安装时，必须给得出人话原因（界面要显示给用户）。"""
    from app.core import update_install as I
    from app.core import updater as U

    ok, reason = I.can_auto_install(U.KIND_SOURCE)
    assert ok is False and "源码" in reason
    # 测试进程本身不是打包版本，所以这里也应当拒绝并给出原因
    ok, reason = I.can_auto_install(U.KIND_ONEDIR)
    assert ok is False and reason


def test_pending_marker_roundtrip():
    """更新标记：写 → 读 → 清，用来判断上次升级到底成没成。"""
    import os

    from app.core import update_install as I

    home = tempfile.mkdtemp(prefix="fusion_pending_")
    saved = os.environ.get("FUSION_MUSIC_HOME")
    os.environ["FUSION_MUSIC_HOME"] = home
    try:
        assert I.read_pending() is None
        assert I.write_pending({"from": "1.0.6", "to": "1.1.0", "kind": "onedir"}) is True
        data = I.read_pending()
        assert data is not None and data["to"] == "1.1.0" and data["at"] > 0
        I.clear_pending()
        assert I.read_pending() is None
    finally:
        if saved is None:
            os.environ.pop("FUSION_MUSIC_HOME", None)
        else:
            os.environ["FUSION_MUSIC_HOME"] = saved


# ──────────────────────────────────────────────────────────────
# 音质档位（漫游曾整条流被判成 320K）
# ──────────────────────────────────────────────────────────────

#: 私人 FM（/api/v1/radio/get）的真实条目骨架：privilege 内联，
#: **没有 sq/sqMusic**，子对象给的是 bitrate 而不是 br —— 就是这三条
#: 让旧实现把每一首都判成"最高 320k"。
_FM_ITEM_HIRES = {
    "id": 2025189982,
    "name": "你看，天又黑了",
    "fee": 8,
    "privilege": {"id": 2025189982, "maxbr": 999000, "playMaxbr": 999000,
                  "playMaxBrLevel": "hires", "maxBrLevel": "hires"},
    "hMusic": {"id": 6945009647, "size": 4966444, "bitrate": 320000},
    "mMusic": {"id": 6945009648, "size": 2979884, "bitrate": 192000},
    "lMusic": {"id": 6945009649, "size": 1986604, "bitrate": 128000},
}
#: 搜索（baseInfo.simpleSongData）的真实骨架：privilege 内联 + hr/sq 子对象
_SEARCH_ITEM_HIRES = {
    "id": 3440441479,
    "name": "晴天",
    "privilege": {"id": 3440441479, "maxbr": 999000, "maxBrLevel": "hires",
                  "playMaxBrLevel": "hires"},
    "hr": {"id": 1, "br": 1497807, "size": 1},
    "sq": {"id": 2, "br": 735085, "size": 1},
    "h": {"id": 3, "br": 320003, "size": 1},
    "m": {"id": 4, "br": 192003, "size": 1},
    "l": {"id": 5, "br": 128003, "size": 1},
}
#: 详情（/api/v3/song/detail）的真实骨架：songs[i] 里没有 privilege，
#: 只有 sq/h/l 子对象，且**无损的 br 远低于 999000**（实测 639052）
_DETAIL_ITEM = {
    "id": 434902428,
    "name": "花火が瞬く夜に",
    "sq": {"id": 11, "br": 639052, "size": 1},
    "h": {"id": 12, "br": 320003, "size": 1},
    "l": {"id": 13, "br": 128003, "size": 1},
}
_DETAIL_PRIVILEGE = {"id": 434902428, "maxbr": 999000, "maxBrLevel": "lossless",
                     "playMaxBrLevel": "lossless"}


def test_wy_quality_types_from_real_shapes():
    """三种真实数据形态都要能判出正确档位（尤其不能把无损漏掉）。"""
    from app.sources.wy import NetEaseMusicSource

    src = NetEaseMusicSource()

    # 私人 FM：以前判成 ['128k','320k']，漫游因此整条流放不到无损
    fm_types = [t["type"] for t in src._parse_types(_FM_ITEM_HIRES)[0]]
    assert fm_types == ["128k", "320k", "flac", "flac24bit"], fm_types

    # 搜索：hr 子对象在 → 有 Hi-Res
    search_types = [t["type"] for t in src._parse_types(_SEARCH_ITEM_HIRES)[0]]
    assert search_types == ["128k", "320k", "flac", "flac24bit"], search_types

    # 详情：sq.br=639052 < 999000，但无损就是无损
    detail_types = [t["type"] for t in src._parse_types(_DETAIL_ITEM)[0]]
    assert detail_types == ["128k", "320k", "flac"], detail_types

    # 什么都没有的裸条目：至少给 128k，别给空列表
    assert [t["type"] for t in src._parse_types({"id": 1})[0]] == ["128k"]

    # 只有 320k 的歌不许被抬成无损
    plain = {"id": 2, "privilege": {"maxbr": 320000, "playMaxBrLevel": "exhigh"},
             "hMusic": {"bitrate": 320000}, "lMusic": {"bitrate": 128000}}
    assert [t["type"] for t in src._parse_types(plain)[0]] == ["128k", "320k"]


def test_wy_merge_privileges_for_detail_response():
    """详情接口把权限放在同级的 privileges 数组里，要能按 id 合上。"""
    from app.sources.wy import NetEaseMusicSource

    src = NetEaseMusicSource()
    merged = src._merge_privileges([dict(_DETAIL_ITEM)], [_DETAIL_PRIVILEGE])
    assert merged[0]["privilege"]["playMaxBrLevel"] == "lossless"
    # 原对象不许被改写（调用方会缓存原始响应）
    assert "privilege" not in _DETAIL_ITEM

    parsed = src._parse_song_detail_songs([dict(_DETAIL_ITEM)], [_DETAIL_PRIVILEGE])
    assert parsed and [t["type"] for t in parsed[0].types] == ["128k", "320k", "flac"]
    # 不传 privileges 时退化（这不是我们要的行为，但也不能抛异常）
    assert src._parse_song_detail_songs([dict(_DETAIL_ITEM)])[0].types


def test_wy_served_level_detection():
    """服务端静默降级要认得出：认不出的 level 一律放行（宁可放，不可误杀）。"""
    from app.sources.wy import _quality_served_rank

    assert _quality_served_rank({"level": "standard"}) == 0
    assert _quality_served_rank({"level": "exhigh"}) == 2
    assert _quality_served_rank({"level": "lossless"}) == 3
    assert _quality_served_rank({"level": "hires"}) == 4
    assert _quality_served_rank({"level": "jymaster"}) == 4
    assert _quality_served_rank({}) > 4          # 没有 level：不拦
    assert _quality_served_rank({"level": "某种新档位"}) > 4


def test_quality_attempt_order_covers_hi_res():
    """Hi-Res 必须在尝试顺序里，否则设置里的「Hi-Res 母带」永远试不到。"""
    from app.sources import RESOLVE_QUALITY_ORDER, _quality_attempt_order

    assert RESOLVE_QUALITY_ORDER[0] == "flac24bit"
    assert _quality_attempt_order("auto") == ["flac24bit", "flac", "320k", "128k"]
    assert _quality_attempt_order("flac24bit")[0] == "flac24bit"
    assert _quality_attempt_order("320k")[0] == "320k"
    # 不认识的档位退回默认顺序，不能抛
    assert _quality_attempt_order("不存在的档位") == RESOLVE_QUALITY_ORDER


def test_effective_quality_reports_what_actually_played():
    """音质标签要以**真正取到地址的那一档**为准，不是"我想要的那一档"。"""
    from app.core.models import Track
    from app.core.resolver import _effective_quality

    track = Track(source="wy", songmid="1", name="x", singer="y",
                  types=[{"type": "128k"}, {"type": "320k"}, {"type": "flac"}])
    # 服务端只给到 320k（实际档位是 320k）→ 如实报 320k
    assert _effective_quality(track, "auto", "320k") == "320k"
    assert _effective_quality(track, "flac", "320k") == "320k"
    # 没有实际档位信息时退回旧口径：auto 用曲目最佳，显式设置回显设置
    assert _effective_quality(track, "auto") == "flac"
    assert _effective_quality(track, "320k") == "320k"


def test_best_quality_prefers_hi_res():
    """曲目行角标用的 best_quality 要能取到最高档。"""
    from app.core.models import Track

    track = Track(source="wy", songmid="1", name="x", singer="y",
                  types=[{"type": "128k"}, {"type": "320k"}, {"type": "flac"},
                         {"type": "flac24bit"}])
    assert track.best_quality == "flac24bit"
    assert track.quality_list == ["128k", "320k", "flac", "flac24bit"]
    assert Track(source="wy", songmid="1", name="x", singer="y").best_quality == "128k"


# ──────────────────────────────────────────────────────────────
# 自定义背景图（设置 → 外观）
# ──────────────────────────────────────────────────────────────


def _write_png(path: Path, width: int = 64, height: int = 48,
               color: tuple = (200, 60, 60)) -> Path:
    """手写一张最小 PNG（纯标准库，测试不想为一张图多要一个依赖）。"""
    import struct
    import zlib

    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
    return path


def _with_background_home():
    """把数据目录指到临时目录（背景图落在 data/backgrounds 下）。"""
    import os

    saved = os.environ.get("FUSION_MUSIC_HOME")
    home = Path(tempfile.mkdtemp(prefix="fusion_bg_"))
    os.environ["FUSION_MUSIC_HOME"] = str(home)
    return home, saved


def _restore_home(saved):
    import os

    if saved is None:
        os.environ.pop("FUSION_MUSIC_HOME", None)
    else:
        os.environ["FUSION_MUSIC_HOME"] = saved


def test_background_store_and_resolve():
    """入库：复制进 data/backgrounds、认出尺寸、名字按内容取（同图不堆副本）。"""
    from app import paths
    from app.core import backgrounds

    home, saved = _with_background_home()
    try:
        paths.ensure_dirs()
        src = _write_png(Path(tempfile.mkdtemp(prefix="fusion_bgsrc_")) / "壁纸.png")
        image = backgrounds.store(src)

        # 注意：data_dir() 会把路径 resolve 一遍，不能拿 mkdtemp 的短路径去比
        assert image.path.parent == paths.backgrounds_dir()
        assert image.path.is_file() and image.size == src.stat().st_size
        assert (image.width, image.height) == (64, 48), (image.width, image.height)
        assert image.url.startswith("file://")
        assert "64×48" in image.info_text

        again = backgrounds.store(src)
        assert again.name == image.name, "同一张图不该产生第二份副本"
        assert len(list(paths.backgrounds_dir().iterdir())) == 1

        resolved = backgrounds.resolve(image.name)
        assert resolved is not None and resolved.name == image.name
        assert backgrounds.resolve("不存在的图.png") is None
        assert backgrounds.resolve("") is None
        assert home is not None
    finally:
        _restore_home(saved)


def test_background_store_rejects_bad_input():
    """入库前的几道闸：体积、内容、路径。文案要能直接给用户看。"""
    from app import paths
    from app.core import backgrounds

    home, saved = _with_background_home()
    try:
        paths.ensure_dirs()
        tmp = Path(tempfile.mkdtemp(prefix="fusion_bgbad_"))

        fake = tmp / "其实是文本.png"
        fake.write_text("这不是图片", encoding="utf-8")
        try:
            backgrounds.store(fake)
            raise AssertionError("伪装成 png 的文本应当被拒")
        except backgrounds.BackgroundError as e:
            assert "图片" in str(e)

        empty = tmp / "空.png"
        empty.write_bytes(b"")
        try:
            backgrounds.store(empty)
            raise AssertionError("空文件应当被拒")
        except backgrounds.BackgroundError:
            pass

        try:
            backgrounds.store(tmp / "根本没有这个文件.png")
            raise AssertionError("不存在的文件应当被拒")
        except backgrounds.BackgroundError:
            pass

        # 体积闸：临时把上限压小，免得真去写 20 MB
        big = _write_png(tmp / "大图.png", 512, 512)
        original = backgrounds.MAX_BYTES
        backgrounds.MAX_BYTES = 64
        try:
            backgrounds.store(big)
            raise AssertionError("超过体积上限应当被拒")
        except backgrounds.BackgroundError as e:
            assert "太大" in str(e)
        finally:
            backgrounds.MAX_BYTES = original

        # 配置里的文件名只允许是"本目录下的普通文件名"
        for name in ("../config.json", "a/b.png", "a\\b.png", ".hidden", ""):
            assert backgrounds.resolve(name) is None, name
        assert list(paths.backgrounds_dir().iterdir()) == []
        assert home is not None
    finally:
        _restore_home(saved)


def test_background_remove_and_prune():
    """换图/清除之后目录里只该留当前那一张，不能每换一次就堆一份。"""
    from app import paths
    from app.core import backgrounds

    home, saved = _with_background_home()
    try:
        paths.ensure_dirs()
        tmp = Path(tempfile.mkdtemp(prefix="fusion_bgprune_"))
        first = backgrounds.store(_write_png(tmp / "a.png", color=(200, 60, 60)))
        second = backgrounds.store(_write_png(tmp / "b.png", color=(60, 120, 200)))
        assert len(list(paths.backgrounds_dir().iterdir())) == 2

        backgrounds.remove(first.name)
        assert backgrounds.resolve(first.name) is None
        backgrounds.prune(keep=second.name)
        assert [p.name for p in paths.backgrounds_dir().iterdir()] == [second.name]

        # 清除背景 = 删文件 + 清目录，重复调用不该报错
        backgrounds.remove(second.name)
        backgrounds.remove(second.name)
        backgrounds.prune()
        assert list(paths.backgrounds_dir().iterdir()) == []
        assert home is not None
    finally:
        _restore_home(saved)


def test_background_config_defaults_are_sane():
    """配置默认值：默认不吃背景图，几个百分比都在 0-100 且互不冲突。"""
    from app.config import DEFAULTS

    appearance = DEFAULTS["appearance"]
    assert appearance["background"] in ("solid", "image")
    assert appearance["background_image"] == ""
    for key in ("background_opacity", "background_blur", "background_scrim",
                "surface_sidebar", "surface_bottom", "surface_overlay", "surface_card"):
        value = appearance[key]
        assert isinstance(value, int) and 0 <= value <= 100, (key, value)
    # 默认值是照「图看清楚、面板别糊住图」定的：背景图给足不透明度、磨砂很轻
    assert appearance["background_opacity"] >= 80
    assert appearance["background_blur"] <= 15
    # 四个分区里内容区的卡片最透、贴着窗口边的播放栏最实
    surfaces = {k: appearance[k] for k in
                ("surface_sidebar", "surface_bottom", "surface_overlay", "surface_card")}
    assert surfaces["surface_card"] == min(surfaces.values()), surfaces
    assert surfaces["surface_bottom"] == max(surfaces.values()), surfaces
    # 未启用图片时，面板必须是实色（否则老用户升级后界面会莫名其妙变透）
    assert appearance["background"] != "image"


# ──────────────────────────────────────────────────────────────
# 逐字（动态）歌词
# ──────────────────────────────────────────────────────────────

#: 网易云真实响应的片段（海屿你 / 1973665667，2026-10 实测）：
#: 逐字行是 ``[行起始,行时长](字起始,字时长,标记)字…``，字与字之间还夹着带时长的空格
YRC_SAMPLE = (
    "[0,1000](0,1000,0) 作词 : Fanko冯思源\n"
    "[13010,4780](13010,660,0)从(13670,670,0)不(14340,30,0) (14370,480,0)主"
    "(14850,610,0)动(15460,30,0) (15490,330,0)示(15820,1070,0)弱(16890,900,0) \n"
    "[17790,1770](17790,170,0)我(17960,450,0)们(18410,290,0)的(18700,470,0)过(19170,390,0)去\n"
)
LRC_SAMPLE = (
    "[00:00.00] 作词 : Fanko冯思源\n"
    "[00:13.47]从不主动示弱\n"
    "[00:17.73]我们的过去\n"
)


def test_lyrics_word_level_keeps_char_ranges_after_trim():
    """``<start,dur>`` 形式的逐字歌词：首尾空白裁掉后，字符区间要跟着平移。

    时间沿用 FMCL 的行为（标记里写多少就是多少，不叠加行时间）—— 这个格式目前
    **没有任何音源在用**（网易云的逐字走 yrc，见下面的用例），保留原语义是为了
    不与 vendored 代码产生行为分叉。
    """
    ly = parse_lyrics("[00:01.00] <0,300>你<300,300>好 \n")
    line = ly.lines[0]
    assert line.text == "你好"
    assert [(w.text, w.char_start, w.char_end) for w in line.words] == [
        ("你", 0, 1), ("好", 1, 2)
    ]
    assert [w.start for w in line.words] == [0, 300]


def test_lyrics_yrc_line_parsing():
    """yrc 直接解析：文本、字符区间、末字时长都要对。

    注意 ``_parse_line`` 会先 ``strip`` 整行，所以 yrc 里的节拍空格只剩行内那些 ——
    生产路径上主歌词另有逐行 LRC（yrc 只提供字时间，见下面的 set_words），
    这里保持"忠实解析"即可。
    """
    ly = parse_lyrics(YRC_SAMPLE)
    assert [l.text for l in ly.lines] == ["作词 : Fanko冯思源", "从不 主动 示弱", "我们的过去"]
    assert [l.time for l in ly.lines] == [0, 13010, 17790]
    assert all(l.word_source == "api" for l in ly.lines)

    line = ly.lines[1]
    # 任何一个字都要占住真实的字符（曾经出现过后缀标记留下的"幽灵字"）
    assert all(w.char_end > w.char_start for w in line.words)
    assert [w.text for w in line.words] == ["从", "不", " ", "主", "动", " ", "示", "弱"]
    # 空格占掉的 30 ms 就是字与字之间的空隙
    assert line.words[2].start == 14340
    assert line.words[2].end == 14370
    # 末字没有自己的标记（`(15820,1070,0)弱` 是最后一个），时长按行尾倒推
    assert line.words[-1].text == "弱"
    assert line.words[-1].start == 15820
    assert line.words[-1].end == 16890


def test_lyrics_set_words_matches_by_text_not_only_time():
    """逐字贴到逐行歌词上：两边行时间差 460 ms 也要认得出是同一行。"""
    ly = parse_lyrics(LRC_SAMPLE)
    assert ly.lines[1].time == 13470          # 逐行歌词自己的时间
    matched = ly.set_words(YRC_SAMPLE)
    assert matched == 3
    # 贴上之后行时间换成 yrc 的（更贴近真实起唱点），行序仍按时间排
    assert [l.time for l in ly.lines] == [0, 13010, 17790]
    assert ly.lines[1].is_word_based
    assert ly.lines[1].words[0].char_end == 1
    # 重建过排序与查找表，index_at 立刻可用
    assert ly.index_at(13010) == 1
    assert ly.index_at(13470) == 1


def test_lyrics_set_words_rejects_mismatched_text():
    """文本对不上就不贴 —— 宁可没有逐字，也不能把别行的时间贴上来。"""
    ly = parse_lyrics("[00:13.47]完全不一样的歌词\n")
    other = "[13010,1000](13010,500,0)从(13510,500,0)不\n"
    assert ly.set_words(other) == 0
    assert ly.lines[0].words == []


def test_lyrics_set_words_ignores_line_already_having_words():
    ly = parse_lyrics(YRC_SAMPLE)
    before = [(w.text, w.start) for w in ly.lines[1].words]
    assert ly.set_words(YRC_SAMPLE) == 0
    assert [(w.text, w.start) for w in ly.lines[1].words] == before


def test_lyrics_pseudo_dynamics_covers_every_character():
    ly = parse_lyrics(LRC_SAMPLE)
    made = ly.apply_pseudo()
    assert made == 3
    for line in ly.lines:
        assert line.word_source == "pseudo"
        assert len(line.words) == len(line.text)
        # 字符区间首尾相接、整数
        assert line.words[0].char_start == 0
        assert line.words[-1].char_end == len(line.text)
        for a, b in zip(line.words, line.words[1:]):
            assert a.char_end == b.char_start
            assert b.start >= a.end          # 不重叠
            assert a.duration >= 0
    # 每字时长按权重分：汉字应该是拉丁字母的两倍
    assert line.words[0].duration == 220


def test_lyrics_pseudo_dynamics_is_capped_and_idempotent():
    """长间奏不拖着填、最后一首按默认时长、重复调用不覆盖真逐字。"""
    ly = parse_lyrics("[00:00.00]第一行\n[01:00.00]第二行\n")
    ly.apply_pseudo()
    first = ly.lines[0]
    assert first.words[-1].end - first.time <= 8000       # 上限
    assert first.words[-1].end - first.time >= 800        # 下限
    # 最后一行没有"下一行"，按默认 5 秒与自然时长取小
    last = ly.lines[1]
    assert last.words[-1].end - last.time <= 5000

    # 已经贴过真逐字的行不受影响
    ly2 = Lyrics()
    ly2.parse(LRC_SAMPLE)
    ly2.set_words(YRC_SAMPLE)
    sources = [l.word_source for l in ly2.lines]
    ly2.apply_pseudo()
    assert [l.word_source for l in ly2.lines] == sources


def test_lyrics_char_progress():
    ly = Lyrics()
    ly.parse(LRC_SAMPLE)
    ly.set_words(YRC_SAMPLE)

    assert ly.char_progress(0) == 0.0            # 第一行还没有逐字进度可言（它是整行）
    assert ly.char_progress(13470) > 0.5         # 第一字唱了一大半
    assert 1.0 <= ly.char_progress(14000) < 2.0
    assert ly.char_progress(15820) == 5.0        # 换到下一个字的瞬间
    # 字与字之间的空隙停在整数上，不会继续往前爬
    assert ly.char_progress(16900) == 6.0
    assert ly.char_progress(17700) == 6.0
    assert ly.char_progress(20000) == 5.0        # 第三行唱完


def test_lyrics_char_progress_without_words_is_zero():
    ly = parse_lyrics(LRC_SAMPLE)
    assert ly.char_progress(13500) == 0.0
    assert ly.char_progress(-100) == 0.0


def test_lyrics_pseudo_progress_walks_the_line():
    ly = parse_lyrics("[00:00.00]甲乙丙丁\n[00:04.00]戊己庚辛\n")
    ly.apply_pseudo()
    assert ly.char_progress(0) == 0.0
    assert 0.0 < ly.char_progress(200) < 1.0
    assert ly.char_progress(2000) == 4.0         # 整行唱完（4 字 × 220 ms）
    # 到下一行的起点就换行了，进度回到新行的 0
    assert ly.char_progress(4000) == 0.0
    assert ly.index_at(3999) == 0 and ly.index_at(4000) == 1


def test_lyrics_offset_shifts_words_too():
    ly = Lyrics()
    ly.parse("[offset:500]\n" + YRC_SAMPLE)
    assert ly.lines[1].time == 13510
    assert ly.lines[1].words[0].start == 13510
    assert ly.lines[1].words[-1].end == 17390


def test_lyrics_to_dicts_marks_dynamic():
    ly = parse_lyrics(LRC_SAMPLE)
    assert all(item["dynamic"] is False for item in ly.to_dicts())
    ly.apply_pseudo()
    assert all(item["dynamic"] is True for item in ly.to_dicts())


# ──────────────────────────────────────────────────────────────
# 封面保存
# ──────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────
# 音频缓存（键与去重）
# ──────────────────────────────────────────────────────────────


def _with_cache_home():
    """把数据目录指到临时目录（音频缓存落在 data/cache/media 下）。"""
    from app import paths

    previous = paths._DATA_DIR_OVERRIDE  # noqa: SLF001 - 只为还原
    home = Path(tempfile.mkdtemp(prefix="fusion_cache_"))
    paths.set_data_dir(home)
    paths.ensure_dirs()
    return home, previous


def test_media_cache_keyed_by_track_identity():
    """同一首歌的不同播放地址只占一份缓存；旧的 URL 键文件会被认领过来。

    背景：网易云的播放地址里嵌着**当前时间戳**
    （``http://m701.music.126.net/20261006125032/…``），同一首歌每次解析出来的
    地址都不一样 —— 按 URL 当键等于每次都新建一份（实测用户盘上 140 个文件里
    44 组内容完全重复，响度分析预取一次、播放又一次）。
    """
    from app import paths
    from app.core import cache

    home, previous = _with_cache_home()
    try:
        url_a = "http://m701.music.126.net/20261006125032/abc/song.mp3"
        url_b = "http://m701.music.126.net/20261006130100/abc/song.mp3"
        identity = cache.media_identity("wy", "1973665667", "320k")
        assert identity == "wy:1973665667:320k"
        # 拿不到曲目身份时退回按 URL 缓存（至少不会串歌）
        assert cache.media_identity("", "", "320k") == ""
        assert cache.media_identity("wy", "", "320k") == ""

        # 旧版本按 URL 存的那份：应当被改名认领到身份键上，而不是重下一遍
        legacy = paths.media_cache_dir() / f"{cache.key_for(url_a)}.mp3"
        legacy.write_bytes(b"audio-bytes")
        first = cache.cached_media(url_a, suffix=".mp3", identity=identity)
        assert first is not None
        assert Path(first).name == f"{cache.key_for(identity)}.mp3"
        assert Path(first).read_bytes() == b"audio-bytes"
        assert not legacy.exists()

        # 地址变了（时间戳不同）仍然命中同一份，不会再存一份
        second = cache.cached_media(url_b, suffix=".mp3", identity=identity)
        assert second == first
        assert len(list(paths.media_cache_dir().iterdir())) == 1
        assert home is not None
    finally:
        paths.set_data_dir(previous)


def test_dedupe_media_removes_only_identical_files():
    """去重只删内容相同的，保留最近用过的那份，删除数与释放字节要报对。"""
    from app import paths
    from app.core import cache

    home, previous = _with_cache_home()
    try:
        base = paths.media_cache_dir()
        payload = b"x" * 4096
        (base / "a.mp3").write_bytes(payload)
        (base / "b.mp3").write_bytes(payload)       # 与 a 完全相同
        (base / "c.mp3").write_bytes(b"y" * 4096)   # 大小相同、内容不同
        (base / "d.flac").write_bytes(b"z" * 100)   # 独一份
        (base / "half.mp3.part").write_bytes(payload)  # 半截文件不参与

        removed, freed = cache.dedupe_media()
        assert removed == 1, removed
        assert freed == 4096, freed
        left = sorted(p.name for p in base.iterdir())
        assert len(left) == 4 and "d.flac" in left and "c.mp3" in left
        assert not ((base / "a.mp3").exists() and (base / "b.mp3").exists())

        # 再跑一次：没有可删的了
        assert cache.dedupe_media() == (0, 0)
        assert home is not None
    finally:
        paths.set_data_dir(previous)


def test_cover_filename_sanitize():
    from app.core.covers import sanitize_filename

    assert sanitize_filename("洛天依 - 达拉崩吧") == "洛天依 - 达拉崩吧"
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"
    # Windows 不允许文件名以点或空格结尾
    assert sanitize_filename("歌名... ") == "歌名"
    # 保留设备名要加前缀，否则在 Windows 上根本建不出来
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("lpt1") == "_lpt1"
    assert sanitize_filename("   ") == "封面"
    assert sanitize_filename("") == "封面"
    long_name = sanitize_filename("啊" * 400)
    assert len(long_name) <= 120


def test_cover_suggest_name_and_suffix():
    from app.core.covers import suggest_stem, suggest_suffix

    assert suggest_stem({"singer": "洛天依", "name": "达拉崩吧"}) == "洛天依 - 达拉崩吧"
    assert suggest_stem({"singer": "", "name": "达拉崩吧"}) == "达拉崩吧"
    assert suggest_stem({"singer": "洛天依", "name": ""}) == "洛天依"
    assert suggest_stem({}) == "封面"

    assert suggest_suffix({"cover": "http://p1.music.126.net/x.jpg"}) == ".jpg"
    assert suggest_suffix({"cover": "http://p1.music.126.net/x.jpg?param=200y200"}) == ".jpg"
    assert suggest_suffix({"cover": "http://x/y.png"}) == ".png"
    assert suggest_suffix({"cover": "file:///D:/music/cover-abc.webp"}) == ".webp"
    assert suggest_suffix({"cover": ""}) == ".jpg"


def test_cover_original_url_strips_resize_hints():
    from app.core.covers import original_url

    assert original_url("http://a/b.jpg?param=200y200") == "http://a/b.jpg"
    assert original_url("http://a/b.jpg?w=200&h=200&x=1") == "http://a/b.jpg?x=1"
    # B站把尺寸写在路径后缀里
    assert original_url("http://i0.hdslb.com/bfs/archive/x.jpg@320w_320h.webp") == \
        "http://i0.hdslb.com/bfs/archive/x.jpg"
    # 认不出来的后缀不动它（有些 CDN 去掉就 403）
    assert original_url("http://a/b?id=7") == "http://a/b?id=7"
    assert original_url("") == ""


def test_cover_detect_suffix_by_magic_bytes():
    from app.core.covers import detect_suffix

    assert detect_suffix(b"\xff\xd8\xff\xe0\x00\x10JFIF") == ".jpg"
    assert detect_suffix(b"\x89PNG\r\n\x1a\n\x00\x00") == ".png"
    assert detect_suffix(b"GIF89a....") == ".gif"
    assert detect_suffix(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"
    assert detect_suffix(b"BM\x00\x00") == ".bmp"
    assert detect_suffix(b"not an image") == ""
    assert detect_suffix(b"") == ""


def test_cover_save_from_local_file_fixes_extension():
    """端到端：从本地 ``file://`` 封面存盘，扩展名按文件头纠正。"""
    from app.core import covers

    tmp = Path(tempfile.mkdtemp(prefix="fusion_cover_"))
    png = _tiny_png()

    src = tmp / "embedded.png"
    src.write_bytes(png)
    track = {"name": "测试曲", "singer": "测试歌手", "source": "local",
             "cover": src.as_uri()}

    dest = tmp / "out" / "手打的名字.jpg"     # 用户给的后缀是错的
    path, size = covers.save_cover(track, str(dest))
    assert size == len(png)
    assert path.endswith(".png"), path          # 按文件头纠正
    assert Path(path).read_bytes() == png       # 原样落盘，不重新编码
    # 不留 *.part 残渣
    assert not list(Path(path).parent.glob("*.part"))


def test_cover_save_reports_missing_cover():
    _expect_cover_error({"name": "没人匹配上的本地曲", "source": "local"}, "x.jpg")


def test_cover_save_rejects_folder_destination():
    tmp = Path(tempfile.mkdtemp(prefix="fusion_cover_"))
    src = tmp / "c.png"
    src.write_bytes(_tiny_png())
    _expect_cover_error({"cover": src.as_uri()}, str(tmp))


def _expect_cover_error(track, destination: str) -> None:
    """断言存封面会以「可读懂的中文原因」失败（不引 pytest，脚本也能直接跑）。"""
    from app.core import covers

    try:
        covers.save_cover(track, destination)
    except covers.CoverError:
        return
    raise AssertionError("应当抛出 CoverError")


def _tiny_png(width: int = 4, height: int = 4) -> bytes:
    """造一张最小的真 PNG（纯标准库），供封面落盘测试用。"""
    import struct
    import zlib

    raw = b"".join(b"\x00" + bytes((10, 20, 30)) * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


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
