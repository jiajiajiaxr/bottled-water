# fish

AgentHub 是一个面向多 Agent 协作的 IM 工作台。它把会话、群聊、Agent 广场、模型管理、工具、Skills、MCP、文件上下文、产物生成、工作流画布和审计权限放在同一套平台里，让用户可以在一个会话中完成“提出任务、编排 Agent、执行工具、审查结果、生成产物、恢复历史”的完整闭环。

平台不是纯演示壳，也不是单一聊天窗口。核心目标是把多 Agent 协作做成可维护的产品形态：会话是入口，画布是编排事实来源，Agent 拥有自己的模型与权限，工具层负责真实执行，产物层负责可预览和可导出。

## 核心理念

- 会话优先：用户从 IM 工作台进入，所有任务都挂在会话或群聊上下文中。
- 画布优先：群聊执行时读取 `conversation.extra.workflow`，按 `nodes` 和 `edges` 执行；Master 只是擅长规划的 Agent，不再拥有隐式最高调度权。
- 权限驱动：Agent 是否能调用工具、Skills、MCP，由自身配置决定；无权限 Agent 是纯对话型，有权限 Agent 才进入短 Agentic Loop。
- 工具真实执行：文件处理、产物生成、MCP 调用、沙箱命令、审查、部署预览等能力统一挂在后端工具层。
- 密钥后端化：模型供应商 API Key 只在后端读取，前端只管理配置与触发测试，不接触真实密钥。

## 功能范围

- 登录、注册、演示用户和用户基础设置。
- 多工作区隔离，会话在不同工作区之间相互独立。
- 左侧 IM 会话侧边栏，支持置顶、归档、分类、搜索、备注和活跃度排序，支持折叠/展开。
- 单聊 Agent 和多 Agent 群聊。
- 模型思考模式开关，支持在聊天中启用/关闭模型的 reasoning 能力。
- 流式回复实时展示模型的思考过程（thinking），可折叠查看。
- 群聊成员管理、群聊命名、分类、备注和会话设置。
- 普通消息、附件消息、流式回复、停止生成和后台任务状态。
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
- 轻量 Dify 风格工作流画布，支持节点增删改、拖拽排序、AI 生成和运行态持久化。
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
  +-- Conversations / Messages / Tasks
  +-- Agents / Models / Skills / MCP / Tools
  +-- Files / Artifacts / Deployments
  +-- Workflow Canvas / Workflow Runs
  |
  v
Orchestration Runtime
  |
  +-- Single Chat: selected Agent loop
  +-- Group Chat: workflow canvas first
  +-- Replan: authorized Agent can rewrite workflow
  +-- Streaming: SSE / WebSocket events
  |
  v
Agentic Tool Loop
  |
  +-- Model Gateway
  +-- Tool Registry
  +-- Skill Runtime
  +-- MCP Runtime
  +-- File Tools
  +-- Artifact Tools
  +-- Sandbox / Remote / Deploy
  |
  v
Persistence
  |
  +-- SQLAlchemy models
  +-- Alembic migrations
  +-- SQLite for local development
  +-- PostgreSQL / Redis compatible design
```

## 前端架构

前端使用 React 18、TypeScript、Vite、pnpm 和 Ant Design。

主要模块：

- `frontend/src/App.tsx`：主应用入口，路由和全局状态初始化。
- `frontend/src/pages/WorkbenchPage`：主工作台，包含三栏布局（侧边栏、聊天区、预览区）。
- `frontend/src/api/`：前端 API SDK，统一封装认证、会话、消息、Agent、模型、工具、Skill、MCP、文件、产物、工作区和审计请求。
- `frontend/src/types/`：领域类型定义，包括会话、消息、Agent、工作流、工具、Skill、MCP、产物等。
- `frontend/src/store/`：Zustand 状态管理，包括会话、消息、任务、产物等 Store。
- `frontend/src/hooks/`：业务 Hooks，包括消息操作、后台任务轮询等。
- `frontend/src/features/`：功能模块组件，包括聊天、预览、平台控制等。
- `frontend/src/styles.css`：IM 工作台、三栏布局、画布、产物预览和管理面板样式。
- `frontend/tests`：Vitest 基础渲染测试。
- `e2e`：Playwright 端到端验收链路。

前端职责是提供成熟工作台体验，不保存模型密钥，不直接执行工具。所有敏感能力都通过后端 API 触发。

## 后端架构

后端使用 Python 3.11、FastAPI、SQLAlchemy、Alembic 和 Pydantic。

主要模块：

- `backend/app/main.py`：FastAPI 应用入口和路由注册。
- `backend/app/core`：配置、数据库、安全、日志、错误处理和统一响应。
- `backend/app/api`：REST、SSE、WebSocket API。
- `backend/app/models.py`：平台数据模型。
- `backend/app/services/chat/orchestrator.py`：多 Agent 编排入口，负责单聊、群聊和工作流触发。
- `backend/app/services/agents/function_loop.py`：单聊和群聊共用的 Agent Function Call Loop。
- `backend/app/services/agents/tool_loop.py`：工具 schema 构造，以及 Tool、Skill、MCP 执行分发。
- `backend/app/services/workflows`：Dify 风格工作流图、调度引擎、节点执行器、运行态和校验。
- `backend/app/services/ark.py`：火山方舟 OpenAI-compatible 模型适配，支持流式输出、工具调用和思考模式。
- `backend/app/services/llm_gateway.py`：模型配置和真实连通性测试。
- `backend/app/services/tools/registry.py`：统一工具目录、内置工具、自定义工具和官方 Agent 工具箱。
- `backend/app/services/tools/executor.py`：工具权限校验、参数校验和执行分发。
- `backend/app/services/file_tools.py`：文件解析、预览、转换、摘要和本地向量入口。
- `backend/app/services/mcp_runtime.py`：MCP 工具调用和调用记录。
- `backend/app/services/artifacts.py`：产物创建、预览卡片和导出入口。
- `backend/app/services/realtime`：SSE 事件总线、消息流和 WebSocket 分发。
- `backend/app/services/queue.py`：异步任务队列。
- `backend/alembic`：数据库迁移。

后端是唯一能访问模型 Key、文件系统、MCP、沙箱和远程资源的层。

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

如果 Agent 没有工具、Skill 或 MCP 权限，它就是纯对话 Agent。

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

Master Agent 是一个普通 Agent，只是默认擅长规划、补全和总结。用户让 Master 或其他 Agent 规划流程时，Agent 可以生成新的 workflow，经后端 normalize 校验后回写到当前会话。

## 工作流画布

workflow 数据保存在 `conversation.extra.workflow`。

节点基础结构：

```json
{
  "id": "agent-frontend",
  "title": "Frontend Worker",
  "type": "agent",
  "role": "frontend",
  "status": "ready",
  "meta": "React UI implementation",
  "agent_id": "agent-id",
  "config": {
    "agent_id": "agent-id",
    "tools": ["file.read", "file.write"],
    "skill_ids": [],
    "mcp_server_ids": []
  }
}
```

运行态保存在 `workflow_runs.node_states`，并同步摘要到 `conversation.extra.workflow_runtime`。

`condition` 节点记录：

```json
{
  "expression": "input.includes('review')",
  "matched_branch": "true"
}
```

`loop` 节点记录：

```json
{
  "max_iterations": 3,
  "current_iteration": 1
}
```

## 官方 Agent 与工具箱

官方 Agent 的工具箱在 `backend/app/services/tools/registry.py` 中维护。

- Master Agent：任务理解、权限判断、规划、补全、聚合。
- Frontend Worker：文件读写、Web App 产物、沙箱运行、浏览器预览。
- Backend Worker：文件读写、数据库检查、沙箱运行、API 测试。
- Reviewer：产物 Diff、测试运行、安全审计、文档审查。
- Deploy Agent：产物导出、部署预览、回滚、沙箱运行。
- Writing Agent：文档结构、PDF、DOCX、PPTX、审稿和修订。
- Daily Chat Agent：日常问答、附件摘要和上下文续聊。

用户创建 Agent 时可以选择底层模型、工具、Skills、MCP 服务和小循环策略。

## 工具层

工具层是 AgentHub 的执行边界。模型只提出意图，真实动作由后端工具执行。

内置工具方向：

- `file.upload`
- `file.extract_text`
- `file.preview`
- `file.convert`
- `file.summarize`
- `file.embed`
- `artifact.create_pdf`
- `artifact.create_docx`
- `artifact.create_xlsx`
- `artifact.create_pptx`
- `artifact.create_html`
- `artifact.create_web_app`
- `artifact.export`
- `artifact.preview`
- `artifact.revise`
- `artifact.diff`
- `sandbox.run`
- `browser.preview`
- `db.inspect`
- `api.test`
- `test.run`
- `security.audit`
- `document.review`
- `deploy.preview`
- `deploy.rollback`

自定义工具保存到数据库，并可由 AI 生成受限 Python 片段写入后端工具工作区。

## 模型接入

模型调用集中在后端。

配置从项目根目录 `.env` 读取：

```env
LLM_PROVIDER=ark
ARK_BASE_URL=...
ARK_ENDPOINT_ID=...
ARK_MODEL=...
ARK_API_KEY=...
DATABASE_URL=...
```

相关代码：

- `backend/app/core/config.py`
- `backend/app/services/ark.py`
- `backend/app/services/llm_gateway.py`
- `backend/app/services/chat/orchestrator.py`
- `backend/app/services/agents/function_loop.py`
- `backend/app/services/agents/tool_loop.py`

`LLM_PROVIDER=ark` 时使用真实火山方舟适配器；`LLM_PROVIDER=mock` 时使用本地模拟响应；`LLM_PROVIDER=auto` 时根据是否存在 Key 自动选择。

## 数据模型

核心表：

- `users`
- `workspaces`
- `workspace_members`
- `agents`
- `conversations`
- `conversation_participants`
- `messages`
- `tasks`
- `subtasks`
- `workflow_runs`
- `artifacts`
- `file_assets`
- `model_providers`
- `model_configs`
- `skills`
- `mcp_servers`
- `mcp_tool_invocations`
- `tool_definitions`
- `sandbox_sessions`
- `deployments`
- `audit_logs`
- `roles`
- `permissions`

## 补充文档

更细的功能说明、文件职责和开发维护资料放在 `docs` 目录：

- `docs/README.md`：文档索引和阅读建议。
- `docs/functional-guide.md`：各功能的使用方式和对应代码入口。
- `docs/file-map.md`：目录、后端 API、service、前端组件和测试文件职责。
- `docs/development-guide.md`：本地开发、迁移、测试和常见改动路径。
- `docs/agent-workflow-runtime.md`：Agentic Loop、群聊画布优先编排和工作流运行态。

## 本地开发

安装后端依赖。后端使用 `uv` 管理 Python 3.11 运行时和依赖锁定：

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

启动后端（推荐在工作区中运行）：

```powershell
cd backend
uv run uvicorn app:app --reload --reload-dir ./app
```

启动前端：

```powershell
cd frontend
pnpm dev
```

### VS Code 工作区

项目根目录提供 `agenthub.code-workspace`，在 VS Code 中打开可直接获得前后端分离的工作区体验：

- **文件夹**：`Backend`（后端）、`Frontend`（前端）、`E2E Tests`（端到端测试）、`Root`（项目根目录）
- **任务**（`Ctrl+Shift+P` → `Tasks: Run Task`）：
  - `Start Backend` — 在 Backend 目录下启动 `uv run uvicorn app:app --reload --reload-dir ./app`
  - `Start Frontend` — 在 Frontend 目录下启动 `pnpm dev`
  - `Start All` — 并行启动前后端
  - `Backend Tests` — 在 Root 目录下运行 `uv run pytest tests -q`
- **调试**（`F5`）：
  - `Debug Backend` — 使用 debugpy 调试 uvicorn，带热重载，排除 logs/ 和 *.db 文件

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

后端使用 Ruff 进行代码检查和格式化：

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

## 近期更新

- **侧边栏折叠**：左侧会话列表支持折叠为 52px 窄工具条，展开后恢复完整视图。
- **消息智能滚动**：消息列表自动保持底部，用户主动向上滚动后暂停自动跟随，回到底部后恢复。
- **流式渲染优化**：delta 批处理窗口从 50ms 降至 16ms（约 60fps），Markdown 解析结果使用 useMemo 缓存。
- **思考模式**：支持在聊天中开启模型思考能力，流式展示 reasoning 过程，可折叠查看。

## 当前边界

- Redis Streams 和 PostgreSQL 是目标架构兼容方向，本地默认可以使用 SQLite 与 asyncio worker。
- MCP 远程执行、沙箱和部署能力保留统一接口，生产级隔离策略仍应由运行环境承载。
- 文件 OCR 和视觉模型入口已预留，具体识别能力取决于配置的模型和后端扩展。
- 工作流画布已支持轻量 Dify 风格节点，但复杂分支可视化、嵌套循环和长任务分布式调度仍可继续增强。
- 思考模式目前依赖豆包/火山方舟模型的 `reasoning_content` 支持，其他模型供应商需适配对应字段。
