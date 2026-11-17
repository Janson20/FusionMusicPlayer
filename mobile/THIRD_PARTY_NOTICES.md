# Android 端第三方依赖与许可

本目录的 Android 客户端整体以 **GPL-3.0-only** 发布（见仓库根 `LICENSE`）。
音源协议与部分行为判据移植自 FMCL 的 `ui/music_source/`（GPL-3.0-only），详见根 `NOTICE.md`。

| 依赖 | 版本 | 许可 |
|---|---|---|
| AndroidX Core / Activity / Lifecycle / Navigation / WorkManager / DocumentFile | 见 `gradle/libs.versions.toml` | Apache-2.0 |
| Jetpack Compose（UI / Foundation / Material 3 / Material Icons） | Compose BOM 2025.10.01 | Apache-2.0 |
| Kotlin / kotlinx.coroutines / kotlinx.serialization | 2.2.x / 1.10.2 / 1.9.0 | Apache-2.0 |
| AndroidX Media3（ExoPlayer / Session / OkHttp DataSource） | 1.11.1 | Apache-2.0 |
| AndroidX CameraX（Core / Camera2 / Lifecycle / View） | 1.4.2 | Apache-2.0 |
| OkHttp | 4.12.0 | Apache-2.0 |
| Coil | 2.7.0 | Apache-2.0 |
| ZXing core | 3.5.4 | Apache-2.0 |
| jaudiotagger（`net.jthink:jaudiotagger`） | 3.0.1 | LGPL-3.0 |

jaudiotagger 源码与许可：
- https://bitbucket.org/ijabz/jaudiotagger
- https://repo1.maven.org/maven2/net/jthink/jaudiotagger/3.0.1/

GPL-3.0 与 LGPL-3.0 兼容；Android 端只通过公开 API 使用 jaudiotagger 的标签读写能力，
未修改其源码。若分发 APK，应同时遵守 LGPL 对库替换/源码获取的要求。

本项目不包含任何来源不明的二进制、反编译源码片段或破解密钥。音源协议常量
（网易云 eapi/weapi 的公开加密参数、B 站 WBI 打乱表等）来自 GPL 授权的 FMCL 实现，
不是破解密钥；QQ QRC / 酷狗 KRC 的加密逐字歌词按合规要求没有接入。
