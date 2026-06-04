# AgentHub

面向多 Agent 协作的 IM 工作台。将会话、群聊、Agent 广场、模型管理、工具、Skills、MCP、文件上下文、产物生成、工作流画布和审计权限放在同一套平台里，让用户可以在一个会话中完成"提出任务、编排 Agent、执行工具、审查结果、生成产物、恢复历史"的完整闭环。

## 核心理念

- **会话优先**：用户从 IM 工作台进入，所有任务都挂在会话或群聊上下文中。
- **画布优先**：群聊执行时读取 `conversation.extra.workflow`，按 `nodes` 和 `edges` 执行；Master 只是擅长规划的 Agent，不再拥有隐式最高调度权。
- **权限驱动**：Agent 是否能调用工具、Skills、MCP，由自身配置决定；无权限 Agent 是纯对话型，有权限 Agent 才进入短 Agentic Loop。
- **工具真实执行**：文件处理、产物生成、MCP 调用、沙箱命令、审查、部署预览等能力统一挂在后端工具层。
- **密钥后端化**：模型供应商 API Key 只在后端读取，前端只管理配置与触发测试，不接触真实密钥。

## 功能范围

- 登录、注册、演示用户和用户基础设置。
- 多工作区隔离，会话在不同工作区之间相互独立。
- 左侧 IM 会话侧边栏，支持置顶、归档、分类、搜索、备注和活跃度排序。
- 单聊 Agent 和多 Agent 群聊。
- 模型思考模式开关，支持在聊天中启用/关闭模型的 reasoning 能力。
- 流式回复实时展示模型的思考过程（thinking），可折叠查看。
- 群聊成员管理、群聊命名、分类、备注和会话设置。
- 普通消息、附件消息、流式回复、停止生成。
- 上传文件在输入框和聊天区展示，文件内容提取后进入模型上下文。
- Agent 广场，包含官方 Agent、自定义 Agent、AI 创建 Agent、编辑 Agent、测试 Agent。
- Agent 可配置底层模型、工具权限、Skill 权限、MCP 权限和 Agentic Loop 策略。
- 官方 Agent 包括 Master Agent、Frontend Worker、Backend Worker、Reviewer、Deploy Agent、Writing Agent、Daily Chat Agent。
- 全局模型管理，支持火山方舟和 OpenAI-compatible 配置。
- Skills 管理，支持手动创建、AI 创建、MCP 导入、测试和删除。
- MCP 服务管理，支持注册、导入、探测、调用、调用记录和删除。
- 工具目录，支持内置工具、自定义工具、AI 生成工具、调用测试和删除自定义工具。
- 文件工具链，覆盖上传、文本提取、预览、转换、摘要和本地向量入口。
- 产物工具链，覆盖 PDF、DOCX、XLSX、PPTX、HTML/Web App 生成、预览、修订、Diff、导出。
- 轻量 Dify 风格工作流画布，支持节点增删改、AI 生成和运行态持久化。
- 工作流节点类型包括 `start`、`agent`、`tool`、`skill`、`mcp`、`condition`、`loop`、`review`、`artifact`、`end`。
- 审计、RBAC、沙箱、远程控制、部署记录和项目文件快照。

## 架构概览

```text
User
  |
  v
React IM Workbench
  |
  v
FastAPI API Layer
  |
  +-- Auth / RBAC / Audit
  +-- Conversations / Messages
  +-- Agents / Models / Skills / MCP / Tools
  +-- Files / Artifacts / Deployments
  +-- Workflow Canvas
  |
  v
Agent Runtime Engine
  |
  +-- Single Chat: SingleAgentScheduler
  +-- Group Chat: WorkflowScheduler (canvas first)
  +-- Multi Agent: TechLeadScheduler (LLM coord)
  +-- Streaming: SSE / WebSocket events
  |
  v
Agentic Tool Loop
  |
  +-- Model Gateway (ark / mock)
  +-- Tool Registry
  +-- Skill / MCP / File / Artifact Runtime
  +-- Sandbox / Remote / Deploy
  |
  v
Persistence
  |
  +-- SQLAlchemy async ORM (db/models/)
  +-- Alembic migrations
  +-- SQLite for local development
```

## 前端

React 18 + TypeScript + Vite + pnpm + Ant Design。

- `frontend/src/App.tsx`：主应用入口，路由和全局状态初始化。
- `frontend/src/pages/WorkbenchPage`：主工作台，三栏布局（侧边栏、聊天区、预览区）。
- `frontend/src/api/`：前端 API SDK，统一封装各类请求和 SSE 流。
- `frontend/src/types/`：领域类型定义。
- `frontend/src/store/`：Zustand 状态管理。
- `frontend/src/features/`：功能模块组件（聊天、预览、平台控制等）。
- `frontend/src/**/*.test.tsx`：Vitest 基础渲染测试。
- `e2e/`：Playwright 端到端验收链路。

## 后端

Python 3.11 + FastAPI + SQLAlchemy (async) + Alembic + Pydantic。

主要模块：

- `backend/src/app/main.py`：FastAPI 应用入口和路由注册。
- `backend/src/app/core/`：配置、安全、日志、错误处理和统一响应。
- `backend/src/app/api/`：REST、SSE、WebSocket API。
- `backend/src/app/services/`：业务服务层。
  - `runtime_service.py`：统一编排入口，创建 AgentSession 并选择调度策略。
  - `agents/function_loop.py` / `agents/tool_loop.py`：Agent Function Calling Loop、能力暴露、工具结果回填。
  - `tools/catalog.py` / `tools/executor.py` / `tools/permissions.py`：工具目录、权限、参数校验和执行记录。
  - `tools/builtins/`：内置 Tool 真实实现，按 artifact、file、sandbox 等领域拆分。
  - `skills/` / `mcp/`：Skill 包运行时与 MCP 服务管理、发现、调用记录。
  - `files/` / `document_model/`：工作区文件树、Office 预览和结构化文档渲染。
  - `llm/ark.py` / `llm/gateway.py`：模型调用网关；`ark.py` / `llm_gateway.py` 仅保留旧导入 shim。
- `backend/src/db/models/`：按领域拆分的数据库模型。
- `backend/src/agent_runtime/`：多智能体运行时引擎（Session、Scheduler、AgentLoop、Workflow）。
- `backend/model_provider/`：大模型提供者抽象。
- `backend/alembic/`：数据库迁移。

`backend/src/` 是当前主架构入口；`backend/app-old/` 仅作为历史实现和迁移参考保留，不再作为新功能开发路径。新增或修复能力时应优先落在 `backend/src/app/api/`、`backend/src/app/services/`、`backend/src/db/models/` 等新结构下。

与本轮迁移相关的核心实现位置：

- 工作区文件系统：`backend/src/app/api/workspace_files.py`、`backend/src/app/services/files/workspace_tree.py`、`frontend/src/features/workspaceFiles/`。
- Office 转 PDF 预览：`backend/src/app/services/files/previewers/office.py`，对外接口为 `/api/v1/artifacts/{artifact_id}/preview-pdf` 和 `/api/v1/workspaces/{workspace_id}/files/preview-pdf`。
- 结构化文档模型：`backend/src/app/services/document_model/`，PDF、Word、PPT/Excel 等产物工具通过 `content_model` 生成真实文件和 HTML/PDF 预览。

后端详情见 `backend/README.md`。

## 编排模型

### 单聊

单聊会话直接启动当前 Agent 的短 Agentic Loop：

```text
User message
  -> selected Agent
  -> Agent model_config_id
  -> Agent tools / skills / mcp permissions
  -> run_agentic_tool_loop(...)
  -> streaming answer
  -> optional artifacts
```

### 群聊

群聊以会话工作流画布为事实来源：

```text
User message
  -> load conversation.extra.workflow
  -> optional replan by authorized Agent
  -> execute workflow nodes by edges/order
  -> agent nodes call corresponding Agent loop
  -> condition / loop / tool / skill / mcp nodes persist runtime state
  -> reviewer / artifact / end nodes produce final response and artifacts
```

Master Agent 是一个普通 Agent，只是默认擅长规划、补全和总结。

## 模型接入

配置从项目根目录 `.env` 读取：

```env
LLM_PROVIDER=ark
ARK_BASE_URL=...
ARK_ENDPOINT_ID=...
ARK_API_KEY=...
DATABASE_URL=...
```

- `LLM_PROVIDER=ark`：真实火山方舟适配器
- `LLM_PROVIDER=mock`：本地模拟响应
- `LLM_PROVIDER=auto`：根据是否存在 Key 自动选择

## 本地开发

安装后端依赖：

```powershell
cd backend
uv sync --extra dev
```

安装前端依赖：

```powershell
cd frontend
pnpm install
```

运行迁移：

```powershell
cd backend
uv run alembic upgrade head
```

启动后端：

```powershell
cd backend
uv run uvicorn app.main:app --reload
```

启动前端：

```powershell
cd frontend
pnpm dev
```

### VS Code 工作区

项目根目录提供 `agenthub.code-workspace`，在 VS Code 中打开可直接获得前后端分离的工作区体验。

## 测试

后端：

```powershell
cd backend
uv run pytest -q
```

前端：

```powershell
cd frontend
pnpm build
pnpm vitest run
```

E2E：

```powershell
cd frontend
pnpm exec playwright test -c ../e2e/playwright.config.ts
```

## 代码规范

后端使用 Ruff：

```powershell
cd backend
uv run ruff check .
uv run ruff format .
```

前端使用 ESLint 和 Prettier：

```powershell
cd frontend
pnpm lint
pnpm format
```

## 补充文档

更细的功能说明、文件职责和开发维护资料放在 `docs/` 目录：

- `docs/functional-guide.md`：各功能的使用方式和对应代码入口。
- `docs/file-map.md`：目录、后端 API、service、前端组件和测试文件职责。
- `docs/development-guide.md`：本地开发、迁移、测试和常见改动路径。
- `docs/agent-workflow-runtime.md`：Agentic Loop、群聊画布优先编排和工作流运行态。
- `docs/implementation-status.md`：文档承诺与当前实现的对照表，区分已完成能力和 roadmap。

## 当前边界

- Redis 和 PostgreSQL 是目标架构兼容方向，本地默认使用 SQLite。
- MCP 远程执行、沙箱和部署能力保留统一接口，生产级隔离策略由运行环境承载。
- 文件 OCR 和视觉模型入口已预留，具体能力取决于配置的模型。
- 思考模式目前依赖豆包/火山方舟模型的 `reasoning_content` 支持，其他模型需适配对应字段。
