# AgentHub Mobile Client

移动端轻量化便捷端口。定位是外出碎片化办公：查看协同会话、核验可视化成果、跟进课题研发进度。

## 能力范围

- 登录：连接 AgentHub 后端账号并同步移动端数据。
- 会话：移动优先的只读协同会话流，适合外出快速跟进。
- 成果：成果卡片快速核验，支持 Web 预览链接和移动安全打开。
- 进度：从后端任务列表同步真实任务状态；没有任务时显示空状态，不生成演示进度。
- 打包：PWA 可添加到主屏幕，Capacitor 同步到 Android / iOS 原生壳。

## PWA 本地运行

```powershell
cd mobile-client
npm install
npm run dev
```

指定端口和后端：

```powershell
.\scripts\run-local.ps1 -Port 5190 -ApiBase "http://127.0.0.1:8000/api/v1"
```

## PWA 可安装构建

```powershell
npm run pwa:installable
```

产物输出在 `mobile-client/dist/`，可放到 CDN、nginx 或任意 Web 容器。浏览器打开后可安装为 PWA；支持离线 app shell 和离线页面。

## Android / iOS 原生壳

一键准备 Android 原生工程：

```powershell
npm run native:prepare
```

手动流程：

```powershell
npm run build
npx cap add android
npm run sync:android
npm run open:android
```

发布路径：

- H5/PWA：`npm run build` 后将 `dist` 放到 CDN 或 Web 容器。
- Android：Capacitor 同步后在 Android Studio 中生成 APK/AAB，接入签名证书。
- iOS：Capacitor 同步后在 Xcode 中归档，接入 Apple Developer Team。

当前仓库已经包含 Android 原生工程目录 `mobile-client/android/`，并可通过 `npx cap sync android` 把最新前端产物同步进去。

## 打包工具链要求

- PWA/H5：Node.js + npm。
- Android：JDK 17+、Android Studio、Android SDK、签名证书。
- iOS：macOS、Xcode、Apple Developer Team。

当前这台机器如果没有 Java / Android SDK，可以构建 PWA 并同步 Android 工程，但不能直接生成 APK/AAB。安装 Android Studio、JDK 17+ 和签名证书后，就可以在 Android Studio 中生成可安装包。

## 同步接口

默认连接：

```text
http://127.0.0.1:8000/api/v1
```

当前已接入真实后端能力：

- `/auth/login`
- `/auth/demo`
- `/auth/me`
- `/conversations`
- `/artifacts`
- `/tasks`
- `/conversations/:id/messages`
- `/conversations/:id/artifacts`
