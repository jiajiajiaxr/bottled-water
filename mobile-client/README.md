# AgentHub Mobile Client

移动端轻量化便捷端口。定位是外出碎片化办公：查看协同会话、确认专项作业审批、核验可视化成果、跟进课题研发进度。

## 能力范围

- 移动优先的会话流和任务进度面板。
- 一键通过 / 驳回审批，离线时先写入本地队列。
- 成果卡片快速核验，支持 Web 预览链接和移动安全打开。
- PWA 离线缓存，桌面添加到主屏幕。
- Capacitor 打包到 Android / iOS 原生壳。

## 商业移动端打包方式

默认先走 PWA + Capacitor：

```powershell
cd mobile-client
npm install
npm run dev
npm run build
npm run sync:android
npm run open:android
```

发布路径：

- H5/PWA：`npm run build` 后将 `dist` 放到 CDN 或 Web 容器。
- Android：Capacitor 同步后在 Android Studio 中生成 AAB，接入签名证书。
- iOS：Capacitor 同步后在 Xcode 中归档，接入 Apple Developer Team。

生产环境建议把 API 地址通过构建环境变量注入，不把密钥、证书或第三方账号配置提交到仓库。
