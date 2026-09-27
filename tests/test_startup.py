"""启动链回归测试：启动画面资源、延迟导入代理、阶段计时。

运行方式::

    python tests/test_startup.py
    pytest tests/test_startup.py

不起 Qt 界面也不联网；启动画面只在 Windows 上做一次真实建窗（几十毫秒，
不会留在屏幕上）。这几条守的都是"改一行就悄悄退化、平时看不出来"的东西：

* ``assets/splash-*.dat`` 与 ``tools/make_splash.py`` 是否还对得上（漂移检查）；
* 预乘 alpha 是否成立（不成立的话启动画面边缘会发白，很显眼但很难查）；
* requests 是不是又被人拉回启动链上了（那 0.4 秒就是这么丢的）；
* 延迟导入代理是不是真的"延迟"。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import startup  # noqa: E402
from app.lazy import LazyModule, loaded, prewarm  # noqa: E402
from app.splash import load_art, read_prefs  # noqa: E402

ASSETS = ROOT / "assets"
THEMES = ("dark", "light")


def test_splash_art_is_consistent_with_generator():
    """仓库里的 .dat 必须与 tools/make_splash.py 的输出逐字节一致。

    底图是**生成物**，改了脚本忘了重新生成，界面就会用旧图 —— 这种漂移
    肉眼很难发现，所以在这里钉死。
    """
    try:
        from tools.make_splash import encode, render
    except ImportError:  # 没装 Pillow（运行时不需要，只有生成/校验才需要）
        print("  跳过：未安装 Pillow")
        return
    for theme in THEMES:
        target = ASSETS / f"splash-{theme}.dat"
        assert target.exists(), f"缺少启动画面资源：{target}"
        assert target.read_bytes() == encode(render(theme), theme), f"{target.name} 已过期"


def test_splash_art_header_and_pixels():
    for theme in THEMES:
        art = load_art(ASSETS / f"splash-{theme}.dat")
        assert art is not None, theme
        assert (art.width, art.height) == (420, 260), (art.width, art.height)
        art_w, art_h = art.art_size
        assert art_w == art.width * 2 and art_h == art.height * 2, art.art_size
        assert len(art.pixels) == art_w * art_h * 4, len(art.pixels)

        # 布局必须落在卡片内部：启动画面按"卡片不透明"来补 alpha，越界就会画出方块
        for name in ("title_rect", "status_rect", "bar_rect"):
            x, y, w, h = getattr(art, name)
            assert 0 <= x and 0 <= y and x + w <= art.width and y + h <= art.height, (name, x, y, w, h)
        assert art.title_px > art.status_px > 0


def test_splash_art_is_premultiplied():
    """UpdateLayeredWindow 要求预乘 alpha：每个像素的 RGB 都不能大于 A。"""
    art = load_art(ASSETS / "splash-dark.dat")
    assert art is not None
    pixels = art.pixels
    for index in range(0, len(pixels), 4 * 997):  # 抽样即可，全量太慢
        b, g, r, a = pixels[index:index + 4]
        assert r <= a and g <= a and b <= a, (index, r, g, b, a)


def test_load_art_rejects_broken_files():
    tmp = Path(tempfile.mkdtemp(prefix="fusion_splash_"))
    assert load_art(tmp / "没有这个文件.dat") is None
    bad = tmp / "bad.dat"
    bad.write_bytes(b"FMPS" + b"\x00" * 200)
    assert load_art(bad) is None
    bad.write_bytes(b"XXXX" + (ASSETS / "splash-dark.dat").read_bytes()[4:])
    assert load_art(bad) is None


def test_read_prefs_follows_config():
    tmp = Path(tempfile.mkdtemp(prefix="fusion_prefs_"))
    # 节名是 appearance（app/config.py 的 DEFAULTS），写错会静默退回"跟随系统"
    (tmp / "config.json").write_text(
        json.dumps({"appearance": {"theme": "light", "accent": "#123456"}}), encoding="utf-8")
    assert read_prefs(tmp) == ("light", (0x12, 0x34, 0x56))

    (tmp / "config.json").write_text(json.dumps({"appearance": {"theme": "dark"}}), encoding="utf-8")
    theme, accent = read_prefs(tmp)
    assert theme == "dark" and accent == (0x6C, 0x4D, 0xF6)

    (tmp / "config.json").write_text(json.dumps({"appearance": {"theme": "auto"}}), encoding="utf-8")
    assert read_prefs(tmp)[0] in THEMES

    # 配置损坏时不许抛异常：启动画面只是"锦上添花"，不能反过来挡住启动
    (tmp / "config.json").write_text("{ 这不是 json", encoding="utf-8")
    assert read_prefs(tmp)[0] in THEMES
    assert read_prefs(tmp / "不存在")[0] in THEMES


def test_lazy_module_defers_import():
    sys.modules.pop("colorsys", None)  # pytest 自己可能已经把它导进来了
    proxy = LazyModule("colorsys")
    assert "colorsys" not in sys.modules
    assert repr(proxy) == "<LazyModule 'colorsys' (未导入)>"
    assert proxy.rgb_to_hls(1.0, 0.0, 0.0) == (0.0, 0.5, 1.0)  # 第一次取属性才真的导入
    assert "colorsys" in sys.modules
    assert "colorsys" in loaded()


def test_prewarm_imports_in_background():
    sys.modules.pop("wave", None)
    # 故意混一个不存在的模块：预热失败只该打一行 stderr，不能把线程带崩
    thread = prewarm("wave", "不存在的模块名")
    thread.join(5)
    assert not thread.is_alive()
    assert "wave" in sys.modules


def test_requests_is_not_on_the_startup_path():
    """核心回归：``import app.application`` 不许把 requests 拉进来。

    它自己就要 0.4 秒（还连带 urllib3 / charset_normalizer / certifi），
    压在启动链上等于让用户白等。必须在**干净的子进程**里测：本进程早就
    因为别的用例把 requests 导进来了。
    """
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "import app.application;"
        "print('PULLED' if 'requests' in sys.modules else 'DEFERRED')" % ROOT
    )
    out = Path(tempfile.mkdtemp(prefix="fusion_lazy_")) / "out.txt"
    with out.open("w", encoding="utf-8") as fh:
        subprocess.run([sys.executable, "-c", code], stdout=fh, stderr=subprocess.STDOUT,
                       cwd=str(ROOT), timeout=180, check=False)
    text = out.read_text(encoding="utf-8", errors="replace")
    assert "DEFERRED" in text, f"requests 又被启动链拉进来了：\n{text[-800:]}"


def test_splash_can_be_disabled_by_env():
    from app import splash

    os.environ["FMP_NO_SPLASH"] = "1"
    try:
        t0 = time.perf_counter()
        assert splash.start(ROOT / "data", ASSETS) is None
        assert (time.perf_counter() - t0) < 0.2
    finally:
        os.environ.pop("FMP_NO_SPLASH", None)


def test_splash_degrades_gracefully_without_win32():
    """非 Windows 上必须"没有启动画面但入口照常"。

    这条守的是**入口的可用性**：``app.splash`` 在模块级用了只有 Windows 才有的
    ctypes.WinDLL，如果不在导入处兜住，Linux 上 ``python main.py`` 会直接
    在 import 阶段炸掉 —— 而不是"少个启动画面"。
    """
    from app import splash

    assert hasattr(splash, "_WINDOWS")
    saved = splash._WINDOWS
    splash._WINDOWS = False
    try:
        assert splash.start(ROOT / "data", ASSETS) is None
        assert splash.load_art(ASSETS / "splash-dark.dat") is not None  # 解析不依赖 Win32
    finally:
        splash._WINDOWS = saved


def test_startup_marks_are_monotonic():
    before = startup.elapsed_ms()
    assert before > 0
    startup.mark("测试阶段")
    after = startup.elapsed_ms()
    assert after >= before
    # 进程创建算起：本测试跑到这儿，肯定已经过去了一点点时间
    assert after > 1.0


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
