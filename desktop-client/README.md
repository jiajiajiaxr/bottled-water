# AgentHub Desktop Client

桌面本地专属客户端。定位是联动本地电脑加密文件资源、系统通知、后台 Agent 算力进程和 Web 主端 API。

## 能力范围

- 本地文件选择、合规登记、AES-256-GCM 加密入库。
- 本地 vault 文件预览，不把原文件路径暴露给渲染进程。
- 系统级通知，用于任务完成、审批提醒和后台 Agent 异常。
- 后台 Agent 进程启动、停止、心跳日志和长效管控。
- 默认连接 `http://127.0.0.1:8000/api/v1`，可在界面里改为云端 API。

## 商业软件打包方式

桌面端使用 Electron + electron-builder：

```powershell
cd desktop-client
npm install
npm run dev
npm run pack:win
```

常见发布形态：

- Windows: NSIS 安装包，支持开始菜单、桌面快捷方式、安装目录选择。
- macOS: DMG / ZIP，后续接入 Apple Developer ID 签名与 notarization。
- Linux: AppImage / deb。

生产环境建议在 CI 中注入代码签名和自动更新配置，不把证书放进仓库。

## 目录

```text
src/main/main.js          Electron 主进程、加密文件库、通知、Agent 进程
src/main/agent-worker.js  本地后台 Agent 进程示例
src/preload/preload.js    安全 IPC 桥
src/renderer/*            桌面端工作台 UI
```
