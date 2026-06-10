# AgentHub

**Language / 语言:** [English](#english) | [中文](#中文)

**Demo / 演示:** [Lightweight static demo](https://jiajiajiaxr.github.io/bottled-water/platform-demo/) · [Local demo guide](./platform-demo/README.md)

---

## English

AgentHub is a multi-agent IM workbench. It combines chat, group collaboration, agent configuration, model providers, tools, skills, MCP servers, workspace files, artifacts, workflow orchestration, audit logs, and preview deployment in one product surface.

### Repository Layout

- `backend/src`: FastAPI, SQLAlchemy, Alembic, runtime services, tools, skills, MCP, files, artifacts, and workflow execution.
- `frontend/src`: React 18, TypeScript, Vite, Ant Design, Zustand, chat workbench, platform panels, preview panel, workflow studio, and docs page.
- `docker/`: one-command local deployment with nginx, backend, PostgreSQL, and Redis.
- `desktop-client/`: lightweight Electron desktop client that wraps the Web app and adds tray, global shortcut, quick input, notifications, and detached windows.
- `mobile-client/`: PWA/Capacitor mobile client for lightweight conversations, artifact review, progress tracking, and installable PWA flow.
- `platform-demo/`: one-command local operational demo for deployment and debugging.

`backend/app-old` is retained only as historical reference. New work should go into `backend/src`.

### What Works Today

- User auth, demo login, workspaces, projects, conversation lists, archive, pin, and category flows.
- Single-agent chat and multi-agent group chat with SSE/WebSocket streaming.
- Model provider configuration, including Ark/OpenAI-compatible model access and mock fallback.
- Agent directory with configurable model, tool, skill, MCP, and loop strategy permissions.
- Built-in tools for files, artifacts, sandbox execution, browser preview, deployment preview, database inspection, security audit, tests, and external coding agents.
- Real external coding agent tool entries for Codex and Claude Code, including probe, run, status, cancel, persisted run records, and tool invocation logs.
- Skills and MCP server management with probe, invocation, and persisted invocation records.
- Workspace files, uploaded attachments, text extraction, preview, Office-to-PDF fallback paths, and knowledge entry points.
- Artifact generation and lifecycle for HTML/Web apps and office/document formats, with preview, edit, diff, export, and deployment preview records.
- Workflow canvas generation, editing, saving, enabling, running, node state persistence, and real tool/agent node execution.
- Security operations panel with audit logs, roles, permissions, and user role updates.
- Docker deployment stack for local or demo environments.
- Desktop, mobile, and platform demo packages for installable or lightweight presentation scenarios.

### Quick Start

Backend:

```powershell
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open the frontend at `http://localhost:5173`.

### Docker Deployment

From the repository root:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

Open `http://localhost`.

To customize passwords, public URL, or exposed port:

```powershell
Copy-Item docker/env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up --build
```

See [docker/README.md](./docker/README.md).

### Demo

- Online static demo: [https://jiajiajiaxr.github.io/bottled-water/platform-demo/](https://jiajiajiaxr.github.io/bottled-water/platform-demo/) (auto-published from `main` via GitHub Actions)
- Local operational demo:

```powershell
.\platform-demo\start.ps1
```

Default local URL: `http://127.0.0.1:4188`.

The static demo can run without a backend. The local demo adds lightweight status, run, event, and artifact APIs for deployment/debugging walkthroughs.

### Client Packages

- `desktop-client/`: Electron desktop client with synchronized Web capabilities plus tray, global shortcut, quick input, notifications, and detached windows.
- `mobile-client/`: PWA/Capacitor mobile client for lightweight conversations, artifact review, installation flow, and progress tracking.
- `platform-demo/`: static-first operational demo for GitHub Pages and local debugging.

### Configuration

The backend reads environment values from the repository `.env`, then `backend/.env`, then process environment.

Common local values:

```env
DATABASE_URL=sqlite:///./agenthub_dev.db
SECRET_KEY=change-me
LLM_PROVIDER=auto
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_API_KEY=
ARK_ENDPOINT_ID=
ENABLE_FUNCTION_CALLING=true
```

For Docker, prefer `docker/.env` based on [docker/env.example](./docker/env.example). The compose file builds the PostgreSQL `DATABASE_URL` from `POSTGRES_*` values so the root development `.env` does not accidentally force SQLite inside containers.

### Tests

Backend:

```powershell
cd backend
uv run ruff check .
uv run pytest -q
```

Frontend:

```powershell
cd frontend
pnpm build
pnpm exec vitest run --config tests/vitest.config.ts
```

### Documentation

- [Docs index](./docs/README.md)
- [Development guide](./docs/development-guide.md)
- [Feature guide](./docs/functional-guide.md)
- [Backend architecture](./docs/backend-architecture.md)
- [Workflow runtime](./docs/agent-workflow-runtime.md)
- [Event protocol](./docs/event-protocol.md)
- [File map](./docs/file-map.md)
- [Capability and data boundaries](./docs/capability-data-boundaries.md)
- [Current implementation status](./docs/implementation-status.md)

---

## 中文

AgentHub 是一个多智能体 IM 协作工作台，把聊天、群聊协作、智能体配置、模型供应商、工具、技能、MCP 服务、工作区文件、成果产物、工作流编排、审计日志和预览部署整合在同一个产品界面里。

### 目录结构

- `backend/src`：FastAPI、SQLAlchemy、Alembic、运行时服务、工具、技能、MCP、文件、产物和工作流执行。
- `frontend/src`：React 18、TypeScript、Vite、Ant Design、Zustand、聊天工作台、平台面板、预览面板、工作流 Studio 和文档页。
- `docker/`：nginx、后端、PostgreSQL、Redis 的一键本地部署栈。
- `desktop-client/`：轻量 Electron 桌面端，封装 Web 应用，并补充托盘、全局快捷键、快速输入、通知和独立窗口。
- `mobile-client/`：PWA/Capacitor 移动端，用于轻量会话、成果核验、进度跟踪和可安装 PWA 流程。
- `platform-demo/`：可本地一键部署调试的平台实操 Demo。

`backend/app-old` 仅作为历史参考保留，新代码请放到 `backend/src`。

### 当前可用能力

- 用户认证、演示登录、工作区、项目、会话列表、归档、置顶和分类。
- 单智能体聊天和多智能体群聊，支持 SSE/WebSocket 流式输出。
- 模型供应商配置，支持 Ark/OpenAI 兼容模型访问和 mock fallback。
- 智能体目录，支持模型、工具、技能、MCP 和循环策略权限配置。
- 内置文件、产物、沙箱执行、浏览器预览、部署预览、数据库检查、安全审计、测试和外部编码智能体工具。
- Codex 与 Claude Code 外部智能体工具入口，包括 probe、run、status、cancel、持久化运行记录和工具调用日志。
- 技能与 MCP 服务管理，支持探测、调用和持久化调用记录。
- 工作区文件、上传附件、文本提取、预览、Office 转 PDF 兜底路径和知识入口。
- HTML/Web 应用和 Office/文档格式产物的生成、预览、编辑、Diff、导出和部署预览。
- 工作流画布生成、编辑、保存、启用、运行、节点状态持久化，以及真实工具/智能体节点执行。
- 安全运营面板，支持审计日志、角色、权限和用户角色更新。
- Docker 本地或演示环境部署栈。
- 桌面端、移动端和平台 Demo 包，覆盖安装包和轻量展示场景。

### 快速启动

后端：

```powershell
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```powershell
cd frontend
pnpm install
pnpm dev
```

浏览器打开 `http://localhost:5173`。

### Docker 部署

在仓库根目录运行：

```powershell
docker compose -f docker/docker-compose.yml up --build
```

打开 `http://localhost`。

如需自定义密码、公开地址或端口：

```powershell
Copy-Item docker/env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up --build
```

更多说明见 [docker/README.md](./docker/README.md)。

### Demo 演示

- 在线轻量静态 Demo：[https://jiajiajiaxr.github.io/bottled-water/platform-demo/](https://jiajiajiaxr.github.io/bottled-water/platform-demo/)（由 `main` 分支通过 GitHub Actions 自动发布）
- 本地实操 Demo：

```powershell
.\platform-demo\start.ps1
```

默认本地地址：`http://127.0.0.1:4188`。

静态 Demo 不依赖后端即可运行；本地 Demo 会额外提供轻量状态、运行、事件和产物 API，方便演示部署与调试流程。

### 客户端与 Demo 包

- `desktop-client/`：桌面端，与 Web 能力同步，并提供托盘、全局快捷键、快速输入、通知和独立窗口。
- `mobile-client/`：移动端/PWA，用于轻量会话、成果核验、安装流程和进度跟踪。
- `platform-demo/`：静态优先的实操 Demo，可用于 GitHub Pages 或本地调试。

### 配置

后端按顺序读取仓库 `.env`、`backend/.env` 和系统环境变量。

常见本地配置：

```env
DATABASE_URL=sqlite:///./agenthub_dev.db
SECRET_KEY=change-me
LLM_PROVIDER=auto
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_API_KEY=
ARK_ENDPOINT_ID=
ENABLE_FUNCTION_CALLING=true
```

Docker 环境建议基于 [docker/env.example](./docker/env.example) 创建 `docker/.env`。Compose 会根据 `POSTGRES_*` 自动组装 PostgreSQL `DATABASE_URL`，避免根目录开发 `.env` 把容器环境误导到 SQLite。

### 测试

后端：

```powershell
cd backend
uv run ruff check .
uv run pytest -q
```

前端：

```powershell
cd frontend
pnpm build
pnpm exec vitest run --config tests/vitest.config.ts
```

### 文档

- [文档索引](./docs/README.md)
- [开发指南](./docs/development-guide.md)
- [功能指南](./docs/functional-guide.md)
- [后端架构](./docs/backend-architecture.md)
- [工作流运行时](./docs/agent-workflow-runtime.md)
- [事件协议](./docs/event-protocol.md)
- [文件地图](./docs/file-map.md)
- [能力和数据边界](./docs/capability-data-boundaries.md)
- [当前实现状态](./docs/implementation-status.md)
