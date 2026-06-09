# AgentHub Desktop Client

轻量桌面客户端。定位类似豆包 PC 客户端：主体能力直接承载 Web 主端，账号、对话、文件、提示词、模型能力、额度和权限规则完全同步；桌面端只补系统级效率能力。

## 和 Web 主端一致的能力

- 同一账号体系，登录状态、会话、文件、收藏和工作区数据走同一套 Web 后端。
- 问答、写作、翻译、代码、图片生成、联网检索、深度思考等 AI 能力不在桌面端重复实现。
- 会员权益、计费规则、模型额度和权限由 Web 主端统一控制。
- 实验功能仍由 Web 主端发布，桌面端加载同一地址即可获得。

## 桌面端增强

- 全局快捷键：默认 `Alt+Space` 呼出悬浮输入框。
- 悬浮输入：在任意软件里输入内容后，会写入当前 AgentHub 聊天输入框。
- 截图问答快捷键：默认 `Alt+Shift+Space` 截取当前屏幕到剪贴板，并把“请分析截图”写入当前聊天输入框。
- 后台常驻：关闭主窗口后留在系统托盘，可继续接收通知。
- 商业化自绘标题栏：无系统默认菜单栏，提供后退、前进、刷新、悬浮输入、截图问答、复制链接、窗口控制。
- 多窗口：从网页打开的新窗口也使用同款自绘标题栏，避免系统默认旧式窗口。
- 原生通知：任务完成、同步异常等可使用系统通知提醒。
- 独立 Chromium：减少浏览器标签页休眠、关闭页面造成的任务中断体验。

## 本地运行

```powershell
cd desktop-client
npm install
npm run dev
```

指定 Web 主端地址：

```powershell
.\scripts\run-local.ps1 -WebAppUrl "http://127.0.0.1:5174"
```

也可以通过环境变量指定：

```powershell
$env:AGENTHUB_DESKTOP_WEB_URL="http://127.0.0.1:5174"
npm run dev
```

## Windows 安装包

```powershell
cd desktop-client
npm run installable:win
```

产物输出在 `desktop-client/release/`：

- `AgentHub Desktop-0.1.0-x64.exe`：NSIS 安装包。
- `AgentHub Desktop-0.1.0-portable-x64.exe`：Portable 免安装包。

## 目录

```text
assets/icon.svg           应用图标
config/default.json       Web 主端地址、快捷键、托盘策略
scripts/build-win.ps1     Windows 安装包构建脚本
scripts/run-local.ps1     本地调试启动脚本
src/main/main.js          Electron 主进程、Web 壳、托盘、快捷键、多窗口
src/preload/preload.js    安全 IPC 桥
src/renderer/*            Web 不可用时的轻量设置页与悬浮输入框
```
