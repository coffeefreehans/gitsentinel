# 🛡️ GitSentinel (Git 哨兵)

> **统一 Git 仓库纳管 · SSH 密钥与凭据安全中心 · 提交前智能拦截确认 · 及时更新与动态桌面提醒**

---

## 🌟 核心功能一览

### 1. 📁 全系统 Git 仓库统一管理
- **自动递归扫描**：启动自动扫描计算机中所有的 Git 仓库（支持配置扫描根目录与深度，支持手动导入任意本地仓库路径）；
- **实时状态总览**：
  - 自动识别当前所在分支、是否有未提交改动（暂存区、工作区、未跟踪文件计数）；
  - 实时显示与远程分支的 **领先 (Ahead) / 落后 (Behind)** 提交数量；
  - 最近一次提交记录（提交信息、作者、相对时间）；
- **快捷操作矩阵**：
  - 一键 `git fetch`、`git pull`、`git push`；
  - 一键在 **Windows 资源管理器**、**系统命令行终端**、**VS Code** 中直接定位打开。

### 2. 🔑 SSH 密钥与凭证中心
- **`~/.ssh` 密钥全景管理**：
  - 自动发现所有公私钥对（`id_ed25519`, `id_rsa` 等）；
  - 自动解析密钥算法类型、长度、SHA256 指纹以及注释/邮箱；
  - 一键复制公钥文本，方便快捷粘贴到 GitHub、GitLab、Gitee 等托管平台。
- **一键生成新密钥**：向导式生成最新推荐的 `Ed25519` 或 `RSA 4096` 密钥对，支持自定义注释与密码保护。
- **平台连通性测试**：一键测试与 **GitHub (`git@github.com`)**、**GitLab (`git@gitlab.com`)**、**Gitee (`git@gitee.com`)** 的 SSH 握手与身份认证状态，实时解析返回当前登录用户名。
- **单仓库专属密钥绑定**：彻底解决多账号（公司账号 vs 个人账号）冲突！为任意仓库一键绑定专用私钥（自动配置 `core.sshCommand`）。
- **Git 全局/局部作者身份切换**：随时查看并一键修改 `user.name` 与 `user.email`。

### 3. 🛡️ Git 提交前智能拦截确认 (Pre-commit Sentinel)
- **多场景全覆盖拦截**：
  - 无论你在 **Windows PowerShell**、**CMD**、**Git Bash**、**VS Code 源码管理面板**、**Cursor**、**IntelliJ / PyCharm** 还是第三方 Git GUI 中执行 `git commit`，都会毫秒级拦截并弹出置顶确认窗口！
- **两种拦截生效模式**：
  - **⚡ 全局拦截模式 (一键开启)**：通过设置 Git 全局 `core.hooksPath`，全系统所有仓库提交时自动受保护；
  - **🎯 单仓库选择性拦截**：仅对你在控制台中开启拦截开关的仓库生效；
- **智能安全合规与敏感泄露扫描**：
  - **高危敏感文件拦截**：自动检测暂存区是否包含 `.env`, `id_rsa`, `*.pem`, `*.key`, `credentials.json`, `token.txt` 等机密配置文件；
  - **代码内机密正则扫描**：在新增代码 (Diff `+`行) 中深度扫描 AWS Access Key、GitHub Token、OpenAI API Key、私钥 Header (`BEGIN PRIVATE KEY`) 等；
  - **强制防呆确认机制**：若检出高危机密，拦截器会亮起红色警报，必须手动勾选“我已知晓风险”复选框后才能确认提交；
- **代码变动 Diff 语法高亮预览**：清晰展示每个变动文件的新增、修改、删除及差异代码；
- **一键放行或阻断**：
  - 点击 `[ ✅ 确认放行 (Proceed) ]`（快捷键 `Enter`）：放行提交，Git 正常生成 Commit；
  - 点击 `[ ⛔ 拦截放弃 (Abort) ]`（快捷键 `Esc`）：阻断提交，退出码 1，命令行与 IDE 明确提示提交已安全取消，工作区代码原封不动！

### 4. 🔔 提交与远程更新及时桌面提醒
- **远程新提交即时预警**：后台静默守护线程定时检查远程仓库状态，当远程分支有新提交可用时，立即触发 Windows 原生 Toast 气泡提醒：
  > *“🔔 仓库 [my-project] 发现远程更新：远程分支有 3 个新提交尚未同步，请及时 Pull 拉取！”*
- **提交完成动态通知**：通过 `post-commit` 钩子，本地成功提交后桌面右下角自动弹出提交成功确认；
- **实时 Web 动态流**：控制台内置 WebSocket 双向通信，所有提交与更新事件实时流式推送到网页端。

---

## 🖥️ 桌面应用程序直接运行 (已编译，开箱即用)

如果你需要真正的图形桌面应用（无需在终端输命令、无需浏览器标签页）：

### 1. Windows 端 (已就绪)
在项目目录 `dist-app\` 中直接双击运行：
- **便携版 (免安装，推荐)**：[`dist-app/GitSentinel 1.0.0.exe`](file:///d:/Projects/wiki-projects/projects/gitsentinel/dist-app/GitSentinel%201.0.0.exe)
  - 零配置，双击立即弹出 GitSentinel 原生暗色窗口与右下角系统托盘！
- **安装版**：[`dist-app/GitSentinel Setup 1.0.0.exe`](file:///d:/Projects/wiki-projects/projects/gitsentinel/dist-app/GitSentinel%20Setup%201.0.0.exe)
  - 经典向导安装，自动生成桌面快捷图标与开始菜单启动项。
- **解包绿色版**：[`dist-app/win-unpacked/GitSentinel.exe`](file:///d:/Projects/wiki-projects/projects/gitsentinel/dist-app/win-unpacked/GitSentinel.exe)

### 2. macOS 端
- 构建命令：`npm run dist:mac`
- 产出文件：`dist-app/GitSentinel-1.0.0.dmg`（直接拖拽到 Applications 安装运行）。

### 3. Linux 端
- 构建命令：`npm run dist:linux`
- 产出文件：`dist-app/GitSentinel-1.0.0.AppImage`（`chmod +x` 后双击直接运行）。

---

## 🚀 启动与使用方式

### 方式一：直接运行已编译的桌面应用程序 (推荐)
直接双击运行上述的 **`GitSentinel 1.0.0.exe`** 或 **`GitSentinel Setup 1.0.0.exe`**，系统将直接唤起 **GitSentinel 原生独立桌面窗口**，自动在后台拉起安全守护进程并在右下角系统托盘驻留盾牌图标。

### 方式二：命令行启动 (开发者模式)
- **Windows**: 双击运行 `start.bat` 或运行 `npm start`
- **macOS / Linux**: 运行终端脚本 `./start.sh` 或 `npm start`

### 2. macOS 打包
在终端执行：
```bash
chmod +x scripts/build_unix.sh
./scripts/build_unix.sh
```
- **生成产物**：
  - `dist/GitSentinel.app`：标准 macOS 应用程序包（内置高分图标与元数据配置）；
  - `dist/GitSentinel-macOS-Universal.zip`：打包归档。

### 3. Linux 打包
在终端执行：
```bash
chmod +x scripts/build_unix.sh
./scripts/build_unix.sh
```
- **生成产物**：
  - `dist/GitSentinel/GitSentinel`：标准 Linux ELF 可执行程序；
  - `dist/GitSentinel/gitsentinel.desktop`：FreeDesktop 桌面快捷启动入口；
  - `dist/GitSentinel-Linux-x86_64.tar.gz`：Linux 发布归档。

### 4. GitHub Actions 自动化 CI/CD 多平台编译
项目内置了完整的 GitHub Actions 工作流配置文件：
👉 [`.github/workflows/build-release.yml`](.github/workflows/build-release.yml)
每当向仓库推送以 `v*` 开头的版本标签（例如 `v1.0.0`）或手动触发 Workflow 时，GitHub Actions 会自动在 Windows、macOS 和 Ubuntu 原生虚拟机中并行编译，并将三平台的可执行应用包自动发布到 GitHub Releases。

---

## ⚙️ 快捷跳过与白名单

如果因自动化脚本部署或紧急情况需要临时绕过拦截确认：
1. **环境变量跳过**：在当前终端设置 `set GIT_SENTINEL_SKIP=1` (PowerShell 中 `$env:GIT_SENTINEL_SKIP="1"`, Bash/Zsh 中 `export GIT_SENTINEL_SKIP=1`)；
2. **Git 原生跳过**：使用 `git commit --no-verify -m "..."`；
3. **单仓库免拦截**：在控制面板中将该仓库的“拦截状态”切换为“旁路”。

---

## 📁 项目工程结构

```
git-sentinel/
├── assets/                      # 应用多分辨率图标资源
│   ├── icon.ico                 # Windows 原生多尺寸应用图标
│   ├── icon.png                 # 高清 512x512 应用图标
│   └── tray_icon.png            # 托盘专用图标
├── backend/
│   ├── app.py                   # FastAPI REST API、WebSocket 广播与跨平台系统操作
│   ├── config.py                # 配置持久化中心 (~/.git-sentinel/config.json)
│   ├── repo_manager.py          # 仓库扫描、状态解析、Ahead/Behind、Hook 生成与赋权
│   ├── key_manager.py           # SSH 密钥解析、生成、平台测试、专属密钥绑定
│   ├── security_scanner.py      # 敏感文件规则与 Token/私钥正则安全扫描引擎
│   ├── notifier.py              # 跨平台系统原生通知中心 (Win Toast / Mac osascript / Linux notify-send)
│   └── background_watcher.py    # 远程分支更新后台自动轮询守护线程
├── interceptor/
│   └── interceptor_gui.py       # 现代化暗色主题置顶拦截确认弹窗 (Tkinter GUI，自适应系统字体)
├── hooks/                       # 全局 Git 钩子目录
│   ├── pre-commit               # 提交前拦截调用入口 (支持冻结二进制与脚本智能路由)
│   └── post-commit              # 提交完成通知入口
├── frontend/
│   └── static/
│       ├── index.html           # 现代化控制台单页应用 (Tailwind CSS + Lucide Icons)
│       └── app.js               # 前端交互与 WebSocket 实时状态流
├── scripts/
│   ├── generate_icons.py        # 矢量与高分辨率图标自动生成脚本
│   ├── build_windows.bat        # Windows 一键打包脚本
│   └── build_unix.sh            # macOS / Linux 一键打包脚本
├── tests/
│   ├── test_integration.py      # 核心拦截生命周期与安全扫描自动化集成测试
│   ├── test_cross_platform.py   # Windows / macOS / Linux 跨平台逻辑与适配测试
│   └── test_api.py              # REST API 与端点回归测试
├── .github/workflows/
│   └── build-release.yml        # GitHub Actions 跨平台自动化构建与发布流水线
├── desktop_app.py               # 现代原生独立桌面窗口应用主入口 (PyWebview + pystray)
├── sentinel.py                  # 统一多合一管理入口与 CLI 调度器
├── package.py                   # 跨平台自动打包主逻辑
├── gitsentinel.spec             # PyInstaller 跨平台打包规格配置
├── requirements.txt             # 项目完整依赖清单
├── pyproject.toml               # Python 项目打包与安装元数据
├── start.bat                    # Windows 一键启动脚本
└── start.sh                     # macOS / Linux 一键启动脚本
```
