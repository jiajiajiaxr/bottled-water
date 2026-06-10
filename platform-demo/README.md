# AgentHub Platform Demo

这是一个可静态托管、也可本地一键联调的平台实操 Demo。

## 静态发布到 GitHub Pages

仓库已经配置 GitHub Actions，会把 `platform-demo/public` 自动发布到 GitHub Pages 的 `/platform-demo/` 路径下。

可托管内容全部在：

```text
platform-demo/public/
```

这个目录是纯静态文件，不需要后端、不需要 Node 服务：

```text
index.html
styles.css
app.js
.nojekyll
```

在 GitHub Pages 上运行时，Demo 会自动进入“静态演示模式”，用浏览器内置模拟数据展示：

- Web 云端主力办公端
- 桌面本地专属客户端
- 移动端轻量化端口
- 多 Agent 任务流
- 成果预览
- 调试日志

## 本地一键调试

如果要演示本地部署调试能力，可以运行：

```powershell
.\platform-demo\start.ps1
```

默认地址：

```text
http://127.0.0.1:4188
```

指定端口：

```powershell
.\platform-demo\start.ps1 -Port 4199
```

本地服务会提供可选调试 API：

```text
GET  /health
GET  /api/status
POST /api/runs
GET  /api/runs/:id
GET  /api/runs/:id/events
GET  /api/artifacts/latest
```

页面会自动检测当前是否有本地 Demo API。如果没有 API，就保持纯静态演示模式。

## GitHub Pages 说明

静态 GitHub Pages 不能直接提供后台任务 API。这个 Demo 已经内置浏览器端任务模拟，所以不影响演示。

如果你想本地修改后重新发布，只要推送 `main` 分支，Pages 工作流就会自动把 `platform-demo/public` 重新部署到：

```text
https://jiajiajiaxr.github.io/bottled-water/platform-demo/
```
