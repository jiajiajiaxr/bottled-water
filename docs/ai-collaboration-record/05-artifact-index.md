# 产物地址索引

## 1. 仓库与代码

| 产物 | 地址/路径 | 说明 |
| --- | --- | --- |
| GitHub 仓库 | `https://github.com/jiajiajiaxr/bottled-water` | AgentHub 主仓库 |
| 后端源码 | `backend/src` | FastAPI、Agent Runtime、Tools、Artifacts、Deployments |
| 前端源码 | `frontend/src` | IM 工作台、文件系统、工作流画布、预览面板 |
| 桌面端 | `desktop-client` | 三端补充能力之一 |
| 移动端 | `mobile-client` | 信息同步与轻量指令入口 |
| 平台演示 | `platform-demo` | 产品演示素材 |

## 2. 文档产物

| 文档 | 路径 | 说明 |
| --- | --- | --- |
| 项目 README | `README.md` | 项目介绍和启动方式 |
| 开发指南 | `docs/development-guide.md` | 本地开发、测试、部署 |
| 后端架构 | `docs/backend-architecture.md` | 服务边界和主链路 |
| Agent 运行时 | `docs/agent-workflow-runtime.md` | 单聊、群聊、工作流、事件语义 |
| 能力边界 | `docs/capability-data-boundaries.md` | Tool / Skill / MCP 数据边界 |
| 文件地图 | `docs/file-map.md` | 主要文件职责 |
| AI 协作记录 | `docs/ai-collaboration-record/` | 本证明包 |

## 3. 演示入口

> 下列地址为本地演示默认值，实际以启动端口为准。

| 入口 | 地址 | 说明 |
| --- | --- | --- |
| Web 工作台 | `http://127.0.0.1:5173/app` | 主力端，完整 IM + 多 Agent |
| 产品发布页 | `http://127.0.0.1:5173/product` | 展示 AgentHub 产品能力 |
| 后端 API | `http://127.0.0.1:8000/api/v1` | FastAPI 接口 |
| API 健康检查 | `http://127.0.0.1:8000/api/v1/health` | 服务状态 |
| 部署预览 | `/api/v1/deployments/{deployment_id}/site/` | 生成产物的可访问 URL |

## 4. 典型演示流程

```text
登录/演示用户
  -> 创建单聊或多 Agent 群聊
  -> 输入复合任务
  -> Team Leader 自动组织
  -> Backend / Frontend / Reviewer / Deploy Agent 协作
  -> 生成文件、HTML、PDF 或项目目录
  -> 点击 preview_card 预览
  -> 点击部署查看真实访问 URL
  -> 工作区文件中查看全部产物
```

