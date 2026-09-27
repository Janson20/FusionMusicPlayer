"""响度实现的**交叉验证**脚本（对照 pyloudnorm / BS.1770 官方系数）。

这个脚本不属于运行依赖：它需要 numpy + scipy + pyloudnorm，而本项目刻意
不引入它们（见 build.spec 的 excludes）。它的用途是在**改过**
``app/core/loudness.py`` 的滤波或门限之后，用一份独立实现校对一遍，例如::

    python -m venv %TEMP%\\fusion_loudness_ref
    %TEMP%\\fusion_loudness_ref\\Scripts\\python -m pip install pyloudnorm numpy scipy
    %TEMP%\\fusion_loudness_ref\\Scripts\\python tools\\validate_loudness.py

校验三件事：

1. 自研的 K 加权系数在 48 kHz 上与 BS.1770-4 附录给出的系数逐位吻合；
2. 单声道 / 立体声正弦、噪声、双电平信号的门限积分响度与 pyloudnorm 一致；
3. 分块（400ms/75% 重叠）与门限口径在「静音 + 短促峰值」这类信号上一致。
"""

from __future__ import annotations

import cmath
import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pyloudnorm as pyln  # noqa: E402

# 按文件路径直接加载：这个校验环境里没有 PySide6，走 app.core 包会连带导入 Qt
_spec = importlib.util.spec_from_file_location(
    "fusion_loudness", ROOT / "app" / "core" / "loudness.py"
)
L = importlib.util.module_from_spec(_spec)
sys.modules["fusion_loudness"] = L      # dataclass 需要在 sys.modules 里找到本模块
_spec.loader.exec_module(L)  # type: ignore[union-attr]

TOL = 0.12          # pyloudnorm 自己也是浮点实现，给 0.12 LU 的容差

# BS.1770-4 附录给出的 48 kHz 系数
REF_SHELF = (1.53512485958697, -2.69169618940638, 1.19839281085285,
             -1.69065929318241, 0.73248077421585)
REF_RLB = (1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)


def _mag(coeffs, freq, rate):
    b0, b1, b2, a1, a2 = coeffs
    z = cmath.exp(-2j * math.pi * freq / rate)
    return abs((b0 + b1 * z + b2 * z * z) / (1 + a1 * z + a2 * z * z))


def check_coefficients() -> list[str]:
    problems = []
    rlb, shelf = L.k_weighting_coeffs(48000)
    for name, mine, ref in (("搁架", shelf, REF_SHELF), ("RLB", rlb, REF_RLB)):
        for i, (a, b) in enumerate(zip(mine, ref)):
            if abs(a - b) > 2e-6:
                problems.append(f"48kHz {name} biquad 系数[{i}] 不符: {a!r} vs {b!r}")
    for f in (20, 100, 1000, 2000, 6000, 12000):
        mine = 20 * math.log10(_mag(shelf, f, 48000) * _mag(rlb, f, 48000))
        ref = 20 * math.log10(_mag(REF_SHELF, f, 48000) * _mag(REF_RLB, f, 48000))
        if abs(mine - ref) > 1e-4:
            problems.append(f"48kHz K 加权幅频 {f}Hz 差 {mine - ref:+.5f} dB")
    print("  [1] 48kHz 系数与幅频：", "一致" if not problems else "有偏差")
    return problems


def _signals():
    rate = 48000
    t = np.arange(rate * 12) / rate
    rng = np.random.default_rng(1234)

    def stereo(mono):
        return np.stack([mono, mono], axis=1)

    yield "1kHz 正弦 -20dBFS", stereo(0.1 * np.sin(2 * np.pi * 1000 * t))
    yield "1kHz 正弦 -33dBFS", stereo(10 ** (-33 / 20) * np.sin(2 * np.pi * 1000 * t))
    yield "997Hz 正弦 满刻度", stereo(np.sin(2 * np.pi * 997 * t))
    yield "白噪声 -12dBFS", stereo(10 ** (-12 / 20) * rng.standard_normal(t.size))
    yield "60Hz 低音 -6dBFS", stereo(0.5 * np.sin(2 * np.pi * 60 * t))
    yield "8kHz 高频 -6dBFS", stereo(0.5 * np.sin(2 * np.pi * 8000 * t))

    # 双电平：前 4 秒 -20dBFS，后 8 秒 -40dBFS（考门限）
    two = np.concatenate([
        0.1 * np.sin(2 * np.pi * 1000 * t[: rate * 4]),
        0.01 * np.sin(2 * np.pi * 1000 * t[: rate * 8]),
    ])
    yield "双电平（门限）", stereo(two)

    # 静音 + 两声短促满刻度（考相对门限）
    sparse = np.zeros(t.size)
    sparse[rate * 3: rate * 3 + rate // 4] = np.sin(2 * np.pi * 1000 * t[: rate // 4])
    sparse[rate * 7: rate * 7 + rate // 4] = np.sin(2 * np.pi * 1000 * t[: rate // 4])
    yield "静音 + 短促峰值", stereo(sparse)


def check_loudness() -> list[str]:
    problems = []
    for rate in (48000, 8000):
        print(f"  [2] 采样率 {rate} Hz")
        for name, data in _signals():
            if rate != 48000:
                # 简易重采样（只用于验证滤波器在不同采样率下的自洽性）
                idx = np.linspace(0, data.shape[0] - 1, int(data.shape[0] * rate / 48000))
                data = np.stack([np.interp(idx, np.arange(data.shape[0]), data[:, 0]),
                                 np.interp(idx, np.arange(data.shape[0]), data[:, 1])], axis=1)
            ref = pyln.Meter(rate, filter_class="DeMan").integrated_loudness(data)
            mine = L.analyze([data[:, 0].tolist(), data[:, 1].tolist()], rate).loudness_lufs
            if mine is None:
                # 双方都判「测不出来」算一致（pyloudnorm 用 -inf，我们用 None）。
                # 8 kHz 采样率下的 8 kHz 正弦就是这种情况：它已经退化成直流。
                if not math.isfinite(ref) or ref <= -70.0:
                    print(f"      {name:<22} pyloudnorm {ref:>8.3f}   自研    None   一致（都判为测不出）")
                    continue
                problems.append(f"{name} @{rate}: 自研测不出响度（pyloudnorm={ref:.2f}）")
                print(f"      {name:<22} pyloudnorm {ref:>8.3f}   自研  None  <-- 不一致")
                continue
            delta = mine - ref
            flag = "" if abs(delta) <= TOL else "  <-- 不一致"
            if flag:
                problems.append(f"{name} @{rate}: 差 {delta:+.3f} LU")
            print(f"      {name:<22} pyloudnorm {ref:>8.3f}   自研 {mine:>8.3f}   差 {delta:+.3f}{flag}")

    # 单声道：整段求和口径相同，应当也一致
    rate = 48000
    mono = (0.2 * np.sin(2 * np.pi * 1000 * np.arange(rate * 5) / rate))
    ref = pyln.Meter(rate, filter_class="DeMan").integrated_loudness(mono)
    mine = L.analyze(mono.tolist(), rate).loudness_lufs
    delta = mine - ref
    print(f"      单声道正弦 @48000        pyloudnorm {ref:>8.3f}   自研 {mine:>8.3f}   差 {delta:+.3f}")
    if abs(delta) > TOL:
        problems.append(f"单声道: 差 {delta:+.3f} LU")
    return problems


def main() -> int:
    print("K 加权与响度的交叉验证（对照 pyloudnorm）\n")
    problems = check_coefficients() + check_loudness()
    print()
    if problems:
        print(f"发现 {len(problems)} 处不一致：")
        for p in problems:
            print("  -", p)
        return 1
    print(f"全部一致（容差 ±{TOL} LU）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
