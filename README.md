# GZHReader

GZHReader 是面向普通用户的 Windows 本地公众号阅读工作台。用户粘贴一篇公众号文章链接后，可以关注对应公众号、接收新文章、生成内容摘要，并在每天指定时间得到 Markdown 简报。

## 产品形态

- Windows 10/11 x64 桌面应用。
- Tauri 2 + Vue 3 工作台。
- Python Core 作为内部 Sidecar，通过 stdin/stdout JSON-RPC 通信。
- 本地 SQLite、FTS5 全文搜索、WAL 和自动备份。
- 直接连接微信读书 Web，不经过 wewe-rss、远程 Bridge 或 RSS 中转服务。
- 不提供网页服务器、公开 HTTP API、CLI、Docker 或 bundled Node runtime。

```text
Tauri 2 + Vue 3
        ↕ JSON-RPC
GZHReader Python Core
        ↓
微信读书 Web
        ↓
SQLite + 内容摘要 + 每日简报
```

## 用户功能

1. 粘贴任意一篇微信公众号文章链接。
2. 确认识别出的公众号。
3. 首次使用时在 Edge 或 Chrome 中扫码连接微信读书。
4. 首次同步近 30 天、最多 20 篇文章。
5. 后续按用户选择的频率自动刷新。
6. 新文章自动生成内容摘要、关键要点、标签和一句话结论。
7. 每天在用户设定的时间生成简报。
8. 关闭主窗口后继续在系统托盘运行。

刷新频率提供 15 分钟、30 分钟、1 小时、2 小时、4 小时和仅手动刷新。每日简报默认在 21:30 生成。

## 内容整理服务

仅支持 OpenAI 兼容接口。设置页只要求：

- 服务地址
- API Key
- 模型名称

内部固定参数为：

- Timeout：90 秒
- Retries：2
- Temperature：0.2

这些参数不会显示在用户界面或普通配置文件中。未配置服务或调用失败时，文章采集仍会继续，并使用本地文本生成临时摘要。

## 本地数据

新版使用独立目录，不迁移或自动删除旧版数据：

```text
%LOCALAPPDATA%\GZHReader\workspace-v3\
  gzhreader.db
  backups\
  browser\
  logs\
  secrets\
```

简报保存到：

```text
%USERPROFILE%\Documents\GZHReader\Briefings\YYYY-MM-DD.md
```

微信读书凭据和摘要服务密钥使用 Windows DPAPI 加密，不以明文写入 SQLite。

## 开发

### 环境

- Windows 10/11 x64
- Python 3.11+
- Node.js 20+
- Rust stable
- Visual Studio Build Tools 2022：MSVC C++ 工具链和 Windows SDK

本机的常规构建工具链安装在：

```text
D:\tools\VSBuildTools2022
E:\sdk\WindowsSDK-10.0.26100.8876
```

Windows SDK 通过系统目录联接注册为 `C:\Program Files (x86)\Windows Kits\10`，实际文件保存在 E 盘。`scripts/build_desktop.ps1` 会自动加载 Visual Studio Build Tools 环境。

### 安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
cd desktop
npm ci
```

### 测试

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m pytest
cd desktop
npm run build
```

### 构建 Sidecar

```powershell
.\scripts\build_sidecar.ps1
```

生成文件：

```text
desktop\src-tauri\binaries\gzhreader-core-x86_64-pc-windows-msvc.exe
```

### 构建桌面安装包

更新包必须签名。把私钥放在仓库外，并设置环境变量：

```powershell
$env:TAURI_SIGNING_PRIVATE_KEY_PATH = "$env:USERPROFILE\.tauri\gzhreader-updater.key"
.\scripts\build_desktop.ps1
```

私钥不得提交到仓库。公开密钥已写入 `desktop/src-tauri/tauri.conf.json`。

## 目录

```text
src/gzhreader_core/       Python 本地核心
desktop/                  Vue/Tauri 桌面应用
scripts/                  Sidecar 与桌面构建脚本
tests/                    Python Core 测试
third_party/licenses/     第三方许可证副本
```

## 第三方代码

微信读书文章解析、分页追赶、节流和错误处理参考并改写自 `rachelos/we-mp-rss` 的 MIT 许可实现。项目不会 import 或运行该仓库。详情见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 注意

微信读书 Web 接口并非稳定公开 API，未来可能发生变化。GZHReader 已实现认证失效停止请求、网络退避、风控冷却和失败不推进游标，但仍需随上游变化维护。

## License

MIT
