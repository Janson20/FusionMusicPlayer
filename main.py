#!/usr/bin/env python3
"""Fusion Music Player —— 入口。

用法::

    python main.py                     # 数据落在程序目录的 data/ 下
    python main.py --data-dir D:\\x     # 自定义数据目录
    FUSION_MUSIC_HOME=D:\\x python main.py

环境变量 ``FUSION_MUSIC_MASTER_PASSWORD`` 可用于启用主密码加密凭据。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

REQUIRED = {
    "PySide6": "PySide6",
    "PySide6.QtQml": "PySide6（QtQml）",
    "PySide6.QtQuick": "PySide6（QtQuick）",
    "PySide6.QtMultimedia": "PySide6（QtMultimedia）",
    "FluentUI": "PySide6-FluentUI-QML",
    "requests": "requests",
    "cryptography": "cryptography",
}

OPTIONAL = {
    "qrcode": "扫码登录",
    "PIL": "扫码登录",
    "mutagen": "读取本地音乐标签与时长",
    "pypinyin": "中文歌单按拼音排序",
}


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _check_dependencies() -> bool:
    """检查依赖是否齐备。

    用 ``importlib.util.find_spec`` 而不是直接 import：后者会真的执行模块代码
    （PySide6 导入开销不小，缺依赖时还会在导入链中间抛异常），而且仅为检查
    存在性的 import 会被静态检查工具误判为未使用导入。
    """
    missing = [label for module, label in REQUIRED.items() if not _has(module)]
    if missing:
        print("缺少依赖：" + "、".join(missing), file=sys.stderr)
        print("请执行:  pip install -r requirements.txt", file=sys.stderr)
        return False

    for module, feature in OPTIONAL.items():
        if not _has(module):
            print(f"提示：未安装 {module}，将无法使用{feature}功能", file=sys.stderr)
    return True


def main() -> int:
    # 启动画面必须赶在**任何重导入之前**：光 requests 就要 0.4 秒、PySide6 还要
    # 0.15 秒，而这期间窗口根本不存在，用户看到的是"点了图标没反应"。
    # 见 app/splash.py（纯 Win32，不用 Qt）。
    from app import paths
    from app.splash import start as start_splash
    from app.startup import mark

    data_dir = paths.pop_data_dir_arg(sys.argv)
    if data_dir:
        paths.set_data_dir(data_dir)
    splash = start_splash(paths.data_dir(), paths.resource_dir() / "assets")
    mark("启动画面已就绪", splash=splash)

    try:
        if not _check_dependencies():
            return 1
        mark("正在加载组件…", splash=splash, progress=0.20)
        from app.application import main as run

        return run(sys.argv, data_dir=data_dir, splash=splash)
    finally:
        # 正常路径上画面早在首帧时就淡出了；这里只兜底早退与异常
        if splash is not None:
            splash.close()


if __name__ == "__main__":
    sys.exit(main())
