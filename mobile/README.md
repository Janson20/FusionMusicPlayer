# Fusion Music Player — Android（mobile/）

原生 Android 客户端，Kotlin + Jetpack Compose + Media3。两端共享同一套 JSON 数据 schema 与音源协议行为；桌面端提供手机扫码登录的一次性凭据移交。

## 当前状态

已完成：

- Gradle 工程、Compose 外壳、五标签导航、三态展开播放页、播放队列页、平板 NavigationRail；点歌曲行会直接进入正在播放页。
- 六个在线音源：网易云、QQ、酷我、酷狗、咪咕、B 站（B 站仅参与跨源兜底）；音源优先级影响搜索排序与跨源兜底。
- 网易云 eapi/weapi 加密、搜索、播放地址、歌词 bundle、扫码/短信/Cookie 登录、资料与远程歌单。
- 从桌面扫码登录：CameraX + ZXing 扫描桌面生成的一次性二维码，AES-256-GCM 解密后导入登录态；二维码 180 秒有效、单次使用，需同一 Wi-Fi。
- 搜索建议（网易云联想）、搜索历史、音源筛选、批量下载；搜索/我的/歌单详情支持多选加入队列、下载或自建歌单。
- Media3 播放服务、媒体通知（上一首 / 播放暂停 / 下一首）、四模式队列、跨源兜底、实际音质上报、会话恢复、切歌淡入与快进/快退步长。
- 播放队列长按拖动排序，行内不再放上移/下移按钮；队列行只保留歌名、歌手、时长与溢出菜单，移除操作放在菜单里。
- 播放页默认显示封面；轻点封面进入歌词；顶部「封面 / 歌词 / 百科」标签可直接切换；在歌词或百科页轻点空白处回到封面。
- 媒体通知使用独立 fusion_playback 通知渠道，暂停/解析中仍保留播放控制；设置页会显示通知是否开启并可直接跳转系统通知设置。
- LRC/YRC 解析、翻译/罗马音、伪动态逐字、Compose 逐字着色、本地音频同目录 `.lrc` 边车优先。
- 我喜欢的音乐、最近播放、自建歌单；发现页推荐/排行榜/新歌；漫游；歌单详情。
- 歌手页、专辑页、歌曲百科：网易云曲目直用 id，其它音源按「歌名 + 歌手 + 时长」定位；原唱标记采用「被翻唱引用的锚点 > 干净锚点 > 有效发布日期最早」的启发式。
- SAF 本地音乐扫描、标签/内嵌封面、在线匹配、本地播放。
- 下载服务：音质降级、文件头/时长校验、标签/封面/歌词、MediaStore/SAF 落盘、任务页、下载后打开文件、可选加入本地曲库。
- Android Keystore / 便携密钥两种凭据保存方式。
- 音量均衡：EBU R128 / BS.1770-4 的 K 加权、400 ms 块 / 100 ms 步进、绝对/相对门限；MediaCodec 解码测量，在线地址最多取前 24 MB；结果缓存到 `data/loudness.json`，播放时经 Media3 `GainProcessor` 应用，并支持目标响度、预增益、是否允许抬升、分析范围、下一首预取、音源级兜底和统计。
- 设置：主题/强调色、自定义背景图/不透明度/磨砂/蒙版、顶栏/底栏透明度、音质、音量/静音、淡入、快退步长、音源开关与优先级、歌词开关/字号/对齐、下载音质/模板/标签/封面/歌词/并发/同名策略、缓存大小与清理、SAF 下载目录、通知权限入口、代理/超时、日志分享、恢复默认、自动更新。
- 自动更新：GitHub Releases 检查、预发布开关、APK 下载进度、SHA-256（GitHub digest 或 `.sha256` 资产）校验、PackageInstaller 安装、未知来源授权引导；调试构建不会尝试覆盖安装。
- GitHub Actions 手动构建：debug/release、可选版本号、Release 上传、APK 重命名与 `.sha256` 生成。

尚未验证或仍待打磨：

- **只完成过一轮真机冒烟**：Gradle 编译、debug APK、R8 release 打包、冷启动、发现页、播放、上一首/下一首和媒体通知控制已验证；网易扫码登录、桌面扫码登录、相机解码、下载、SAF、MediaStore、jaudiotagger、Keystore 与音量均衡仍需要完整设备回归。
- 部分音源（QQ 签名兜底、B 站）边界；通知封面首次播放时仍可能先用远程 URI，下载完成后缓存供后续使用；没有设备回归。
- 自定义下载目录的 SAF 授权可能被系统或文件提供方回收；下载失败会在任务页显示错误，重新在「设置 → 存储与缓存 → 下载目录」选择目录即可。
- 下载歌词优先写 `MediaStore.Files` 的 `Music/FusionMusicPlayer`，系统不允许时退到 `Download/FusionMusicPlayer`；歌词写入失败只记日志，不会把已完成的音频任务标记为失败。
- 原唱标记没有移植桌面的策展表、百科兜底和全部特殊规则；当前是结果页内的启发式。
- 桌面歌词/系统托盘/Win32 启动画面不适用于 Android；桌面歌词/全局热键桌面端本来也未实现。
- GitHub Actions 尚未在仓库中实际触发；首次运行需按日志校验 SDK、签名和 Release 步骤。

这份状态会随实现更新；没有验证过的项不会写成已完成。

## 构建

需要 JDK 17、Android SDK Platform 36、Build-Tools 36.0.0。

```bash
cd mobile
./gradlew :app:assembleDebug
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

本地 `local.properties` 不要入库；用 `ANDROID_HOME` 或 `sdk.dir` 指定 SDK。

Release 构建需要签名环境变量，否则只产出 unsigned APK：

```bash
export ANDROID_KEYSTORE_PATH=/path/release.jks
export ANDROID_KEYSTORE_PASSWORD=...
export ANDROID_KEY_ALIAS=...
export ANDROID_KEY_PASSWORD=...
./gradlew :app:assembleRelease
```

## GitHub Actions（手动触发）

`.github/workflows/android.yml` 只有 `workflow_dispatch`：

| 输入 | 说明 |
|---|---|
| `variant` | debug / release |
| `version` | 可选；不填读取 `app/_version.py` |
| `publish_release` | 是否把 APK 上传到 GitHub Release |
| `release_tag` | publish_release=true 时必填；Release 不存在时会创建 |

签名 secrets：

- `ANDROID_KEYSTORE_BASE64`
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

生成 keystore（只做一次，务必自己备份）：

```bash
keytool -genkeypair -v -keystore release.jks -alias fusion \
  -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 release.jks > release.jks.b64
```

把 base64 内容和三个密码填进仓库 Secrets；`*.jks`、`*.keystore` 已在 `.gitignore` 中。

发布资产命名为 `FusionMusicPlayer-<version>-<variant>.apk`，并生成同名 `.sha256`。自动更新只接受非 debug 的 APK；没有 SHA-256 时拒绝安装。

## 数据目录

App 私有目录下的 `data/` 与桌面端同名同结构：

```
files/data/config.json
files/data/credentials.enc
files/data/keys/master.key
files/data/playlists.json / favorites.json / history.json / local.json
files/data/session.json
files/data/downloads.json
files/data/loudness.json
files/data/background.img
files/data/cache/{cover,lyric,media,downloads,loudness}
files/data/updates/
files/data/logs/fusion.log
```

下载默认写系统媒体库 `Music/FusionMusicPlayer`（Android 10+ 无需存储权限）；`storage.download_dir` 以 `content://` 开头时写 SAF 目录。Android 9 及以下若授予写入权限，则写公共 `Music/FusionMusicPlayer` 并触发媒体扫描；拒绝时自动退到应用专属外部目录。系统媒体库写入失败时也会退到应用专属外部目录，并在下载任务页显示提示，不会直接把已下载音频丢掉。不申请全盘音频/存储权限，本地音乐通过 SAF 目录授权。

## 权限

- INTERNET / ACCESS_NETWORK_STATE
- FOREGROUND_SERVICE / FOREGROUND_SERVICE_MEDIA_PLAYBACK / FOREGROUND_SERVICE_DATA_SYNC
- POST_NOTIFICATIONS（Android 13+，用于播放、下载与更新通知）；未授权时媒体通知不会出现，可在应用「设置 → 通知」查看状态并跳转系统设置。
- WAKE_LOCK
- CAMERA（仅「从电脑扫码」页使用，不保存相机画面）
- REQUEST_INSTALL_PACKAGES（应用内更新安装 APK）
- WRITE_EXTERNAL_STORAGE（仅 Android 9 及以下，`maxSdkVersion=28`；用于写公共音乐目录。Android 10+ 使用 MediaStore，不申请）

不申请 READ_MEDIA_AUDIO / WRITE_EXTERNAL_STORAGE。

## 已知边界

- 第三方音乐接口不是稳定 API；客户端只做重试/降级，不保证永远可用。
- 桌面扫码登录要求手机与电脑在同一局域网；桌面只接受私网 IPv4，不提供公网中继。
- 二维码只在 App 内扫描；没有注册系统深链。自定义 scheme 可能被恶意 App 抢注，因此不把携带临时密钥的二维码交给系统相机/第三方扫码器。
- 手机与桌面共享 `MUSIC_U`；如果网易续期会立即作废旧 token，两端自动续期可能互相踢下线，需真机验证。
- 部分媒体 CDN 仍是 http；客户端 API/登录强制 HTTPS，媒体允许明文以保证兼容（凭据不走明文）。
- 标签写入使用 jaudiotagger 3.0.1（LGPL-3.0），只走二进制 Artwork，不调用 AWT 图像接口；写入失败不影响音频下载。
- 自动更新只支持侧载 APK，不上架 Google Play；需要用户允许「安装未知应用」。
- 音量均衡对在线曲目先下载最多 24 MB 再解码，长曲目标记为「前一段」并使用更保守的峰值上限；测量失败会缓存 24 小时再重试。
- 桌面歌词、系统托盘、Win32 启动画面不适用于 Android；对应能力由媒体通知/MediaSession 承担。

## 依赖许可

见 `THIRD_PARTY_NOTICES.md`。整体仍为 GPL-3.0-only；音源协议来自 FMCL，详见根 `NOTICE.md`。
