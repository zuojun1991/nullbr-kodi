# NullBR Kodi 影音库 - 自动播放方案

> 在线点播 https://nullbr.eu.org 的海量影视库（优先播放UHD杜比原盘iso），自动完成转存和云下载。

---

## 目录 <a id="toc"></a>

* [架构简介](#arch)
* [准备工作](#prep)
* [依赖与兼容性](#deps)
* [第一步：获取 NullBR API](#nullbr-api)
* [第二步：获取 115 Cookies 与云下载 CID](#p115-cookie-cid)
* [第三步：部署后端服务器（选择其一）](#deploy)

  * [路径 A：Alist + rclone（进阶）](#path-a)
  * [路径 B：CD2 / 直接挂载（简化）](#path-b)
  * [路径匹配与常见示例（**强烈建议阅读**）](#path-match)
  * [CD2 在 Docker 下的填写示例](#path-cd2-docker)
  * [在 CoreELEC（CE）下的填写示例](#path-ce)
* [第四步：安装与配置 Kodi 插件](#kodi-setup)
* [第五步：设置开机自启](#autostart)
* [FAQ / 常见坑位排查](#faq)
* [支持本项目](#support)

---

## 🏗️ 架构简介 <a id="arch"></a>

**数据流**：`Kodi 插件 (UI) ↔ 后端服务器 (核心) ↔ 115 网盘 (存储) ↔ 挂载工具（Alist/CD2/rclone） ↔ Kodi 播放器`

* **Kodi 插件**：展示影视列表，向后端发起播放请求。
* **后端服务器**：对接 NullBR 与 115 API，完成资源选源、转存/离线、回传可播放路径。
* **115 网盘**：承载你的媒体。
* **Alist / CD2 / rclone**：把网盘“变成本地/局域网可访问的目录（或 SMB 共享）”，让 Kodi 能直接读文件。

> 目标是实现“即点即播”：点击影视条目 → 自动转存/离线 → Kodi 直接播放。

[返回目录↑](#toc)

<img width="490" height="250" alt="image" src="https://github.com/user-attachments/assets/5440af5e-406f-4afc-98c1-bcddff0c50d8" />
<img width="300" height="300" alt="image" src="https://github.com/user-attachments/assets/f4a9775f-08e6-473c-96fc-57d9e6bdd30b" />

---

## 🛠️ 准备工作 <a id="prep"></a>

* 一台安装好 **Kodi** 的设备（Windows, macOS, Linux, Android TV, CoreELEC 等）。
* 一个 **115** 账号。
* 一台常驻运行的设备部署**后端服务器**（电脑/NAS/树莓派均可）。

[返回目录↑](#toc)

---

## 📦 依赖与兼容性 <a id="deps"></a>

**最低 Kodi 版本**：`19 (Matrix)` 或更高——因为 `addon.xml` 里要求 `xbmc.python` **3.0.1**（Kodi 自带的 Python API 版本）。

**依赖（按 `addon.xml`）：**

```xml
<requires>
    <import addon="xbmc.python" version="3.0.1"/>
    <import addon="script.module.requests" version="2.31.0"/>
    <import addon="script.module.simplecache" version="1.0.0"/>
</requires>
```

* `xbmc.python ≥ 3.0.1`：**内置于 Kodi**，无需手动安装；只需保证 Kodi 版本满足（Matrix 及以上）。
* `script.module.requests ≥ 2.31.0`：可从 GitHub Release 安装 zip（见下方下载索引），或从 Kodi 官方库安装（若版本满足）。
* `script.module.simplecache ≥ 1.0.0`：同上。

**安装顺序建议**（从 ZIP 安装时）：

1. 先安装 `script.module.requests` → 2) 再安装 `script.module.simplecache` → 3) 最后安装本插件 zip。

> 提示：若你的设备启用了 Kodi 官方仓库且版本满足，直接在**附加组件**里搜索安装依赖更轻松。

**下载索引（示例模板，按你的 GitHub 仓库替换 `<owner>/<repo>` 与 zip 文件名）：**

* Requests：`https://github.com/<owner>/<repo-requests>/releases/latest/download/script.module.requests-2.31.0.zip`
* SimpleCache：`https://github.com/<owner>/<repo-simplecache>/releases/latest/download/script.module.simplecache-1.0.0.zip`
* 本插件：`https://github.com/<owner>/<repo-addon>/releases/latest/download/plugin.video.nullbr.zip`

> 若你已经有现成的下载地址，把上面的模板链接替换成真实地址即可。

[返回目录↑](#toc)

---

## 🔑 第一步：获取 NullBR API <a id="nullbr-api"></a>

1. **注册与申请**：访问 NullBR 官网，注册并申请开发者权限。
2. **创建应用**：在后台创建应用；描述要清晰、有目的（例如仅供个人 Kodi 使用），避免“test/测试”等无意义词。
3. **获取密钥**：审核通过后，拿到 `APP_ID` 与 `API_KEY`。
4. **列表 ID**：在文档页挑选想看的列表，记录其 ID（逗号分隔），示例：`2142788,2142753`。

[返回目录↑](#toc)

---

## 🍪 第二步：获取 115 Cookies 与云下载 CID <a id="p115-cookie-cid"></a>

* **Cookies**：浏览器登录 115 后，通过开发者工具（Network → Request Headers）复制 `cookie:` 的值；或参见 Alist 官方 115 挂载向导的扫码流程。
* **云下载 CID**：进入 **云下载** 文件夹，浏览器地址栏 `cid=` 后面的数字即为该文件夹 CID。

[返回目录↑](#toc)

---

## 🖥️ 第三步：部署后端服务器（选 A 或 B） <a id="deploy"></a>

### 路径 A：Alist + rclone（进阶） <a id="path-a"></a>

1. **安装 Alist** → 添加 115 存储 → 记下 **Alist Token**。
2. **安装 rclone** → `rclone config` 里新增 `alist` 类型 remote（假设命名为 `alist115`）。
3. **挂载示例（Windows）**：

```bat
@echo off
chcp 65001
C:\rclone\rclone.exe mount alist115: F:\rclone_alist ^
  --rc --rc-addr 127.0.0.1:5572 ^
  --vfs-cache-mode=full --cache-dir="F:\rclone-cache" ^
  --vfs-cache-max-size=200G --vfs-cache-max-age=24h ^
  --dir-cache-time=15s --vfs-read-chunk-size=32M ^
  --vfs-read-chunk-size-limit=1G --multi-thread-streams 3 --transfers 4 --no-traverse
pause
```

4. **后端配置片段**：

```python
# ===== 基本配置 =====
P115_COOKIE = "<你的 115 Cookies>"
TARGET_CID  = "<云下载 CID>"   # 注意：这里填云下载 CID
ALIST_BASE  = "http://127.0.0.1:5244"
ALIST_TOKEN = "<Alist Token>"
SMB_BASE    = "smb://192.168.1.3/f/rclone_alist"  # rclone 挂载目录对应的 SMB 共享
```

> `SMB_BASE` 是 **Kodi 将要访问的路径前缀**；它必须与共享出来的路径一致。

[返回目录↑](#toc)

---

### 路径 B：CD2 / 直接挂载（简化） <a id="path-b"></a>

* 简化版 `server.py` 仅负责 115 的转存/离线，不再操纵 Alist/rclone；**你只需保证 Kodi 能访问到网盘文件夹**。

```python
# ===== 基本配置（简化版） =====
P115_COOKIE = "<你的 115 Cookies>"
TARGET_CID  = "<云下载 CID>"
# 不需要 Alist / rclone 配置
```

> **最关键**：插件设置中的 **Rclone Mount Path** 必须与**实际挂载路径**严格一致（见下文示例）。

[返回目录↑](#toc)

---

## ✅ 路径匹配与常见示例（强烈建议阅读） <a id="path-match"></a>

**原则**：Kodi 插件里的 `Rclone Mount Path`（名字沿用，但不限 rclone）要与**你在系统/局域网里暴露出来的浏览路径完全一致**。后端只会在这个基础路径上**拼接** `云下载/文件名.mkv`。

> 也就是说：**你填的是“根路径前缀”**，插件会把 `云下载/xxx` 拼在它后面。

**速查表**：

| 部署位置                | 实际挂载（本机）            | 通过 SMB 共享名         | 插件里应填写（示例）                               |
| ------------------- | ------------------- | ------------------ | ---------------------------------------- |
| Windows 主机 + rclone | `F:\rclone_alist`   | 共享为 `f`（或子目录）      | `smb://192.168.1.3/f/rclone_alist/`      |
| Linux/NAS 主机 + CD2  | `/mnt/cd2/115/`     | 共享为 `cd2`          | `smb://192.168.1.10/cd2/115/`            |
| NAS 主机 + 直连 115     | `/volume1/115/`     | 共享为 `115`          | `smb://nas.local/115/`                   |
| 与 Kodi 同机（本地路径）     | `/storage/cd2/115/` | 共享为 `cd2`（见 CE 小节） | `smb://<本机IP>/cd2/115/` （**推荐**）或本地绝对路径* |

* 若使用本地绝对路径，需要确保插件/播放器能直接访问该路径；SMB 更通用稳妥。

[返回目录↑](#toc)

---

## 🐳 CD2 在 Docker 下的填写示例 <a id="path-cd2-docker"></a>

> 下述思路适用于 Linux/NAS 等环境，**关键是把 CD2 的“挂载点”映射为宿主可见路径，并以 SMB 共享出去**。

1. **确保 CD2 会把 115 映射到宿主目录**（如 `/mnt/cd2/115/`）。
2. **把 `/mnt/cd2` 共享为 SMB 名称**（比如 `cd2`）。
3. **插件填写**：`Rclone Mount Path = smb://<宿主IP>/cd2/115/`

> 如果你的 CD2 只把“云下载”目录单独映射为 `/mnt/cd2/云下载/`，那就把共享根设到 `/mnt/cd2/`，插件仍填 `smb://<IP>/cd2/`，后端会继续拼接 `云下载/`。

**容器参数提示**：

* 需要 FUSE 权限（容器通常要 `--cap-add SYS_ADMIN --device /dev/fuse`）。
* 把容器内挂载点（例如 `/CloudNAS`）映射到宿主（例如 `/mnt/cd2`）。
* 后续通过 Samba 导出 `/mnt/cd2` 即可。

[返回目录↑](#toc)

---

## 📺 在 CoreELEC（CE）下的填写示例 <a id="path-ce"></a>

> 目标：让 Kodi 能以 **稳定的网络路径** 访问 115 内容。CE 自带 Samba 服务，可将本地目录分享为 `smb://<CE 主机名或 IP>/<共享名>/`。

**推荐做法**：

1. 把 CD2（或其它挂载工具）把 115 映射到 CE 本地目录，例如：`/storage/cd2/115/`。
2. 在 CE 的 Samba 配置里把 `/storage/cd2` 暴露为共享名 `cd2`（可通过自定义 `samba.conf` 或 Web 配置）。
3. 插件填写：`Rclone Mount Path = smb://<CE-IP>/cd2/115/`

> 也可以直接填写本地路径（如 `/storage/cd2/115/`），但当你以后把 Kodi 迁移到其他设备时，SMB 路径更具可移植性。

**常见坑**：

* 共享名或大小写不一致（Windows 与 *nix 大小写敏感差异）。
* CE 上的防火墙/局域网隔离导致 SMB 访问失败。
* Kodi 添加网络源时能看到，但插件里写的前缀不同步（多了/少了一个子目录）。

[返回目录↑](#toc)

---

## 🧩 第四步：安装与配置 Kodi 插件 <a id="kodi-setup"></a>

> 安装插件前，建议先完成依赖安装（见上文 [依赖与兼容性](#deps)）。

1. 安装 zip：Kodi → 插件 → 从 ZIP 安装（也可使用 Release 中的 zip）。
2. 在插件**设置**中填写：

   * **NullBR**：`App ID`，`API Key`，`List IDs`（逗号分隔）。
   * **TMDB API** '' 可填写在api.themoviedb.org申请的api，这样主页海报墙可以获取更多内容（clearlogo，同人画） 此项目需要做好host映射或者代理
   * **Server**：`Transfer Server URL`（例：`http://192.168.1.3:3000`）。
   * **Rclone Mount Path**：

     * 路径 A：填 **SMB_BASE**（例：`smb://192.168.1.3/f/rclone_alist/`）。
     * 路径 B：填 CD2/直连的**实际挂载路径**（例：`smb://192.168.1.10/cd2/115/`）。
   * **115 Cloud Credentials**：可选；通常服务端已使用，插件可留空。

[返回目录↑](#toc)

---

## 🚀 第五步：设置开机自启 <a id="autostart"></a>

**Windows**：用 `.bat` + `vbs` 隐藏窗口，放到 `shell:startup`。

```bat
:: start_server.bat
@echo off
cd /d "C:\path\to\server"
python server.py
```

```vb
' autostart.vbs
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\path\to\start_rclone.bat""", 0, False
WshShell.Run """C:\path\to\start_server.bat""", 0, False
```

**Linux / CE**：建议用 `systemd`；也可在 CE 的自启动脚本里拉起 mount 与 server（参考你设备的发行版文档）。

[返回目录↑](#toc)

---

## ❓FAQ / 常见坑位排查 <a id="faq"></a>

* **点了目录跳不到标题？**

  * 本文所有目录使用**自定义锚点**（如 `#path-b`），在 GitHub/Gitea/大多数渲染器里都可稳定跳转，即使标题含中文/Emoji。
* **插件显示“找不到文件”**？

  * 99% 因为 `Rclone Mount Path` 与实际共享前缀不一致。对照上表逐级核对：IP/主机名、共享名、子目录是否一致，末尾是否需要 `/`。
* **CD2 Docker 能看到文件，但 Kodi 访问不到**？

  * Docker 内的挂载要映射到**宿主路径**，并由宿主通过 Samba 分享；Kodi 访问的是宿主的 SMB，不是容器内路径。
* **CloudDrive/Alist/rclone 刷新延迟导致文件不可见**？

  * 等待目录缓存刷新，或在 rclone 开启 `--rc` 后由后端触发刷新；Alist 端也注意目录缓存时间。

[返回目录↑](#toc)

---

## ❤️ 支持本项目 <a id="support"></a>
![微信图片_20251030013522_16_264](https://github.com/user-attachments/assets/720fb244-4f34-4dd0-9b84-9967d0ed2264)


如果本方案对你有帮助，可以考虑请作者喝杯咖啡 ☕。

[返回目录↑](#toc)
