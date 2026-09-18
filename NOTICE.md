# 来源与许可声明

## 本项目

Fusion Music Player 采用 **GPL-3.0-only** 许可（见 `LICENSE`）。

## 来自 FMCL 的部分

`app/sources/` 目录下的以下文件取自
[FMCL（Fusion Minecraft Launcher）](https://github.com/Janson20/FMCL) 的
`ui/music_source/` 包，作者 Janson20，同样以 GPL-3.0-only 发布：

| 本仓库文件 | 上游文件 | 改动 |
|---|---|---|
| `app/sources/base.py` | `ui/music_source/base.py` | 仅把包内 import 改为相对导入 |
| `app/sources/utils.py` | `ui/music_source/utils.py` | 无改动 |
| `app/sources/wy.py` | `ui/music_source/wy.py` | 仅把包内 import 改为相对导入 |
| `app/sources/kw.py` | `ui/music_source/kw.py` | 同上 |
| `app/sources/kg.py` | `ui/music_source/kg.py` | 同上 |
| `app/sources/mg.py` | `ui/music_source/mg.py` | 同上 |
| `app/sources/tx.py` | `ui/music_source/tx.py` | 同上 |
| `app/sources/bili.py` | `ui/music_source/bili.py` | 同上 |

`app/sources/__init__.py` 中的跨源兜底算法（`resolve_track` /
`_quality_attempt_order` / `duration_matches` 的调用约定）同样移植自 FMCL，
但**音源注册表改为惰性实例化**——FMCL 在 import 时构造全部音源，其中
`BiliBiliMusicSource` 的构造函数会同步请求 `https://www.bilibili.com`（超时 12 秒），
导致启动阻塞。

`app/core/resolver.py` 中的音频文件头校验与时长校验判据
（`ID3` / `fLaC` / `OggS` / `RIFF` / `MP3` 裸帧 / `ftyp`，以及
`max(10s, 期望时长 × 0.2)` 的容差）同样取自 FMCL。

`app/core/lyrics.py` 的三个 LRC 正则与时间计算规则（毫秒右侧补零、
一行多标签展开、全局 `offset` 叠加、负值钳零）取自 FMCL 的 `ui/music_lyrics.py`。

**其余代码**（QML 界面、播放引擎、队列、歌单与历史存储、凭据加密仓库、
账号管理、缓存、桥接层、设置系统）均为本项目重新实现，未复制 FMCL 的
`customtkinter` UI 或 `pygame` 播放后端。

## 为什么上游是 GPL 而本项目也是 GPL

GPL-3.0 具有传染性：分发包含 GPL 代码的衍生作品时，整体必须以 GPL-3.0 授权
并提供源码。本项目通过 `app/sources/` 直接内联了 FMCL 的网易云协议实现，
因此整体采用 GPL-3.0-only 是必须的，而非可选。

如果将来需要改用更宽松的许可（如 MIT），必须先把 `app/sources/` 中来自 FMCL
的部分替换为独立实现。

## 第三方依赖

| 依赖 | 许可 |
|---|---|
| PySide6 / Qt for Python | LGPL-3.0 / 商业 |
| [PySide6-FluentUI-QML](https://github.com/zhuzichu520/FluentUI) | MIT |
| requests | Apache-2.0 |
| cryptography | Apache-2.0 / BSD |
| mutagen | GPL-2.0-or-later |
| qrcode | BSD |
| Pillow | HPND |
| pypinyin（可选） | MIT |
