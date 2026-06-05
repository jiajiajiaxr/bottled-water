# 文件职责地图

本文说明主要目录和关键文件负责什么，方便二次开发时快速定位。

## 顶层目录

```text
agenthub/
  backend/      FastAPI 后端、SQLAlchemy 模型、Alembic 迁移、服务层
  frontend/     React + TypeScript + Vite + Ant Design 前端
  docs/         项目补充文档
  e2e/          Playwright 端到端测试
  tests/        后端 pytest 测试
  scripts/      验收和辅助脚本
  infra/        基础设施预留目录
  var/          本地运行数据、上传文件、AI 生成工具、日志
```

> 说明：`backend/src/` 是当前后端主架构目录；`backend/app-old/` 仅用于对照历史实现和迁移遗漏，不应作为新代码入口。文档中提到后端 API、服务和模型时，默认都指向 `backend/src/app/`、`backend/src/db/` 和 `backend/src/agent_runtime/`。

## 后端入口

- `backend/src/app/main.py`：FastAPI 应用入口，注册 CORS、异常处理、健康检查和所有 API 路由。
- `backend/main.py`：兼容启动入口，转发到 `app.main`。
- `backend/alembic.ini`：Alembic 配置。
- `backend/alembic/env.py`：迁移运行环境，读取 SQLAlchemy metadata。
- `backend/alembic/versions/*.py`：数据库迁移脚本。
- `backend/pyproject.toml`：后端项目元数据、运行依赖和开发依赖。
- `backend/uv.lock`：uv 锁文件，保证依赖解析可复现。
- `backend/.python-version`：uv 使用的 Python 版本约束。

## 后端 core

- `backend/src/app/core/config.py`：统一配置。当前只读取项目根目录 `.env` 和 `backend/.env`，不读取项目外层目录。
- `backend/src/db/session.py`：SQLAlchemy async engine、AsyncSessionLocal、get_db。
- `backend/src/db/base.py`：DeclarativeBase、TimestampMixin、uuid_str、utcnow。
- `backend/src/app/core/security.py`：密码哈希、JWT 创建和解析。
- `backend/src/app/core/errors.py`：业务异常类型。
- `backend/src/app/core/response.py`：统一响应结构。

## 后端模型

所有主要数据库表定义在 `backend/src/db/models/` 下，按领域拆分。

核心模型分组：

- 用户与权限：`User`、`UserSettings`、`Role`、`Permission`、`UserRole`、`RolePermission`
- 工作区：`Workspace`、`WorkspaceMember`、`Project`、`ProjectFile`
- Agent：`Agent`、`AgentCapability`
- 会话：`Conversation`、`ConversationParticipant`、`Message`、`MessageVersion`
- 编排：`Task`、`Subtask`、`TaskDependency`、`WorkflowRun`
- 文件与产物：`FileAsset`、`Artifact`、`ArtifactVersion`、`Deployment`
- 模型：`ModelProvider`、`ModelConfig`
- 扩展：`Skill`、`ToolDefinition`、`McpServer`、`McpToolInvocation`
- 安全执行：`SandboxSession`、`RemoteConnection`、`AuditLog`
- 知识库：`KnowledgeBase`、`KnowledgeDocument`

## 后端 API

- `backend/src/app/api/auth.py`：注册、登录、演示登录、当前用户、修改资料、改密码。
- `backend/src/app/api/workspaces.py`：工作区、成员、项目文件、提示词模板、快捷命令。
- `backend/src/app/api/conversations.py`：会话创建、编辑、分类、归档、删除、成员、工作流画布、工作流运行态。
- `backend/src/app/api/messages.py`：消息列表、发送、重试、回复、SSE 流、停止生成。
- `backend/src/app/api/agents.py`：Agent 广场、创建、AI 生成、编辑、删除、测试、能力解析。
- `backend/src/app/api/models.py`：模型供应商、模型配置、模型测试。
- `backend/src/app/api/files.py`：文件上传、列表、下载、提取文本、预览、摘要、向量入口、转换、删除。
- `backend/src/app/api/artifacts.py`：产物创建、获取、预览、保存版本、Diff、导出、兼容附件接口、知识库兼容接口。
- `backend/src/app/api/workspace_files.py`：工作区文件树、预览、下载、Office PDF 预览、删除、重命名、新建目录、移动、收藏和批量删除。
- `backend/src/app/api/knowledge.py`：知识库、文档导入、上传和检索。
- `backend/src/app/api/skills.py`：Skill 创建、AI 生成、MCP 导入、测试、删除；测试入口统一调用 `SkillRuntime` 并写入 `SkillRun`。
- `backend/src/app/api/mcp.py`：MCP 注册、导入、更新、探测、工具列表、工具调用、调用记录、删除。
- `backend/src/app/api/tools.py`：工具目录、创建工具、AI 生成工具、编辑、删除、调用。
- `backend/src/app/api/sandbox.py`：沙箱和远程连接管理。
- `backend/src/app/api/deployments.py`：部署预览、部署记录、回滚。
- `backend/src/app/api/security_ops.py`：审计日志、角色、权限、用户权限后台。
- `backend/src/app/api/context.py`：上下文接口。
- `backend/src/app/api/websocket.py`：WebSocket 连接入口。

## 后端 services

- `backend/src/app/services/runtime_service.py`：统一编排入口。负责创建 AgentSession、选择调度策略（单 Agent / TechLead / Workflow）。
- `backend/src/app/services/chat/scheduling.py`：消息级、会话级调度策略的统一解析入口。单聊固定 `single_agent`，群聊默认 `tech_lead + actor`，只有 `workflow_enabled=true` 才进入 workflow。
- `backend/src/agent_runtime/`：核心运行时。WebSocket 对话主链路都进入这里，包含 Session、SchedulerAgent、AgentLoop、Actor Runtime、Workflow 图遍历等。
- `backend/src/agent_runtime/core/protocol.py`：异步多 Agent Runtime 事件协议常量。
- `backend/src/agent_runtime/runtime/event_dispatcher.py`：运行时 EventBus，兼容 sink dispatch，并支持 publish/subscribe/target routing。
- `backend/src/agent_runtime/runtime/mailbox.py`：Agent / Scheduler inbox。
- `backend/src/agent_runtime/runtime/agent_stepper.py`：兼容旧 AgentLoop 的 step 间控制层。
- `backend/src/agent_runtime/runtime/agent_actor.py`：独立 asyncio Task Agent actor。
- `backend/src/agent_runtime/runtime/actor_orchestrator.py`：事件驱动 Actor Runtime 生命周期管理，是默认群聊自动组织的运行容器。
- `backend/src/agent_runtime/strategies/scheduler_agent.py`：事件驱动 Team Leader / Scheduler actor。订阅用户输入、Agent 报告、Blackboard 更新和失败事件，发布 `scheduler.decision` 与 `control.assign`。
- `backend/src/app/services/runtime/generation_records.py`：把旧 Orchestrator 和新 Actor Runtime 的 generation、AgentRun、调度决策、watchdog、取消事件折叠进 `Conversation.extra.runtime`，供刷新恢复和前端运行态展示使用。
- `docs/runtime-async-closure-2026-06-05.md`：记录本轮异步 Actor Runtime 的已落地能力、验证覆盖和仍需长期演进的边界。
- `backend/src/app/services/agents/function_loop.py`：Agent Function Calling Loop。根据 Agent 权限暴露 Tool、Skill、MCP，执行 tool_calls 并把结果回填模型。
- `backend/src/app/services/agents/tool_loop.py`：同步 Function Call 工具 schema 构造、授权校验、Tool / Skill / MCP 执行分发。
- `backend/src/app/services/agents/async_tool_loop.py`、`async_tool_selection.py`：AsyncSession-backed V2 runtime adapter 的工具暴露、选择和执行分发。
- `backend/src/app/services/agentic_runtime.py`：旧运行时兼容 shim，纯 re-export 到 `agents/async_tool_loop.py`，不包含业务逻辑。
- `backend/src/app/services/llm/ark.py`：火山方舟和 OpenAI-compatible 模型适配，包括普通调用、流式调用和 mock fallback；`services/ark.py` 仅保留旧导入 shim。
- `backend/src/app/services/llm/gateway.py`：模型配置测试和模型调用统一入口；`services/llm_gateway.py` 仅保留旧导入 shim。
- `backend/src/app/services/tool_registry.py`：兼容 shim，纯 re-export 到 `tools/legacy_registry.py`。新代码使用 `backend/src/app/services/tools/catalog.py`、`executor.py`、`permissions.py`。
- `backend/src/app/services/tools/legacy_registry.py`：历史 awaitable registry API 适配层，用于旧集成兼容；不承载新的工具业务逻辑。
- `backend/src/app/services/tools/builtins/`：内置工具真实实现，按 artifact、file、sandbox 等复杂能力拆分目录。
- `backend/src/app/services/file_tools.py`：文件工具兼容入口，核心能力已迁到 `services/tools/builtins/file/` 和 `services/files/`。
- `backend/src/app/services/files/`：工作区文件树、文件引用解析、Office 预览和文件类 Tool 支撑。
- `backend/src/app/services/document_model/`：结构化文档模型、Markdown 解析、模板、PDF/DOCX 渲染和 HTML 预览。
- `backend/src/app/services/artifacts.py`：产物对象创建和基础内容组织。
- `backend/src/app/services/artifact_exports.py`：产物导出兼容入口，核心导出在 `services/tools/builtins/artifact/export.py`。
- `backend/src/app/services/deployments.py`：预览部署创建、产物可访问性健康检查、部署步骤和日志生成。
- `backend/src/app/services/skills/`：Skill manifest、依赖检查、可恢复版本快照、case 级测试报告和 `prompt/agent/mcp/script` runner。
- `backend/src/app/services/mcp_runtime.py`：MCP 兼容入口，核心目录、JSON-RPC `tools/list` 探测、transport 和调用在 `services/mcp/`。
- `backend/src/app/services/knowledge.py`：轻量知识库切片、索引、检索和上下文片段构造。
- `backend/src/app/services/realtime/event_bus.py`：事件总线，优先 Redis PubSub，缺省使用内存队列；用于 SSE/实时状态。
- `backend/src/app/services/queue.py`：后台任务队列，优先 Redis，缺省使用内存队列。
- `backend/src/app/services/audit.py`：权限判断和审计日志写入。
- `backend/src/app/services/serialization.py`：后端模型转前端 JSON，负责敏感字段脱敏。
- `backend/src/app/services/output_filter.py`：过滤内部任务拆解、执行过程、审查草稿等不该直接展示给用户的文本。
- `backend/src/app/services/seed.py`：初始化演示用户、工作区、官方 Agent、模型、角色、权限和基础数据。

## 后端 schemas

- `backend/src/app/schemas/common.py`：通用 schema。
- `backend/src/app/schemas/requests.py`：请求体 schema，覆盖 Agent、模型、工具、Skill、MCP 等创建和测试请求。

## 前端入口

- `frontend/src/main.tsx`：React 应用挂载入口。
- `frontend/src/App.tsx`：React Router 外壳入口。
- `frontend/src/router/`：登录、工作台、文档等顶层路由。
- `frontend/src/pages/WorkbenchPage/`：工作台状态中心和布局，组合会话、聊天、预览、Agent 广场、设置和平台控制等模块。
- `frontend/src/api/`：前端 API SDK，统一封装 token、请求、fallback、SSE 流、文件下载和 mock 数据兜底。
- `frontend/src/types/`：前端领域类型定义。
- `frontend/src/styles/`：布局、IM 工作台、消息、侧边栏、画布、抽屉、产物预览等样式。
- `frontend/src/mock.ts`：前端离线 fallback 数据，主要用于后端不可用时不让界面完全空白。

## 前端 App.tsx 内主要组件

- `LoginScreen`：登录、注册、演示用户入口。
- `Workbench`：主工作台状态中心，管理会话、消息、文件、产物、工作区和后台任务。
- `AgentDirectoryDrawer`：Agent 广场，支持查看、创建、AI 创建、编辑、测试、删除 Agent。
- `MembersDrawer`：群聊成员管理。
- `ConversationSettingsDrawer`：会话设置和群聊工作流画布。
- `CreateConversationModal`：新建单聊或群聊。
- `GlobalSettingsDrawer`：全局设置，包含模型、MCP、工具、Skills、用户设置。
- `PlatformControlDrawer`：平台控制，包含工作区、沙箱、远程连接、安全审计等。
- `frontend/src/features/platform/components/SecurityOpsPanel.tsx`：安全运营面板，展示审计统计/详情、角色目录，并支持用户角色变更。
- `PreviewPanel`：产物预览、编辑、Diff、导出。
- `BackgroundTasksButton`：后台任务入口。

## 测试文件

- `tests/conftest.py`：后端测试 fixture，创建测试数据库和 FastAPI client。
- `tests/test_auth.py`：注册、登录、演示用户。
- `tests/test_auth_settings.py`：用户资料和密码设置。
- `tests/test_conversation.py`：会话、成员、分类、工作流。
- `tests/test_message.py`：消息发送、流式、附件。
- `tests/test_artifact.py`：产物创建、版本、Diff、预览。
- `tests/test_deployment.py`：部署记录。
- `tests/test_tools_files.py`：文件工具和工具目录。
- `tests/test_skills.py`：Skill 创建、测试、删除。
- `tests/test_model_mcp_sandbox.py`：模型、MCP、沙箱。
- `tests/test_platform_extensions.py`：平台扩展能力。
- `tests/test_workspace_security_deploy_task.py`：工作区、权限、部署、后台任务。
- `frontend/src/**/*.test.tsxapp-render.test.tsx`：前端基础渲染测试。
- `e2e/agenthub-demo.spec.ts`：端到端演示链路。

## 运行数据目录

- `var/storage/uploads`：本地上传文件。
- `var/ai-tools/generated`：AI 生成或用户创建的 Python 工具片段。
- `var/backend.log`、`var/backend.err.log`：后端运行日志。
- `var/frontend.log`、`var/frontend.err.log`：前端运行日志。

`var` 是本地运行数据目录，里面的内容不属于核心源码。

## MCP 调用链路文件

- `backend/src/app/services/mcp/invocation.py`：MCP 调用记录、allowlist/schema 预检、transport 分发、错误码归一和审计。
- `backend/src/app/services/mcp/transports/common.py`：工具名、allowlist 和安全环境变量处理；显式 disabled 工具优先于通配符。
- `backend/src/app/services/mcp/transports/http.py`：HTTP JSON-RPC MCP 调用，包含 timeout、request error 和鉴权错误诊断。
- `backend/src/app/services/mcp/transports/stdio.py`：受控 stdio MCP 子进程调用。
- `backend/src/app/services/mcp/transports/sse_ws.py`：SSE/WebSocket MCP transport 占位降级入口，当前返回清晰未启用错误并写入调用记录。
## 2026-06-05 External Coding Agent 文件地图

- `backend/src/app/services/external_agents/base.py`：定义 Codex / Claude Code 等外部 Coding Agent 的统一 Adapter 协议，包括探测、启动、取消和事件流。
- `backend/src/app/services/external_agents/registry.py`：注册 `codex` 与 `claude_code` adapter，后续接入其他长任务 Coding Agent 时从这里扩展。
- `backend/src/app/services/external_agents/process_manager.py`：受控子进程执行器，强制 `shell=False`、数组 argv、超时、取消、stdout/stderr 流读取和密钥脱敏。
- `backend/src/app/services/external_agents/workspace.py`：把运行目录限制在当前 workspace/conversation/agent 的 `tools/` 子目录内，并只返回相对变更文件。
- `backend/src/app/services/external_agents/adapters/codex.py`、`adapters/claude_code.py`：CLI 适配器。真实 CLI 缺失时返回 degraded，不假装成功。
- `backend/src/app/services/tools/builtins/external_agent.py`：把外部 Agent 映射为内置 Tool：`external_agent.probe/run_codex/run_claude_code/cancel/status`。
- `backend/src/app/api/external_agents.py`：前端管理页使用的探测与运行记录 API，不返回 API Key、token 或本地登录态。
- `backend/alembic/versions/9f1c2d3e4a5b_external_agent_runs.py`：新增 `external_agent_runs` 运行记录表。
- `frontend/src/features/settings/components/ExternalAgentsPanel/`：全局设置中的“外部 Agent”管理卡片，展示安装/降级状态与最近运行记录。
- `frontend/src/api/externalAgent.ts`、`frontend/src/types/externalAgent.ts`：前端 API SDK 与类型定义。
- `backend/tests/test_external_agents.py`、`frontend/tests/external-agents-panel.test.tsx`：fake executable 与管理卡片测试，不依赖真实 Codex / Claude Code CLI。
## 2026-06-05 工具产物稳定性文件地图

- `backend/src/app/services/runtime_service.py`：Agent Runtime 的 ToolExecutor 适配层；负责把 runtime tool call 路由到 app 工具系统，并在 artifact 工具成功后推送真实 `artifact:created/message:new`。
- `backend/src/app/services/tools/builtins/artifact/executor.py`：内置 artifact.create_* 的真实文件生成、Artifact 持久化和 preview_card 创建；preview_card 字段必须包含主格式下载信息。
- `backend/src/app/services/artifacts.py`：旧 async artifact 创建入口的 preview_card 兼容逻辑。
- `backend/src/app/api/workspace_files.py` 与 `backend/src/app/services/files/previewers/office.py`：工作区文件预览、Office 转 PDF 缓存与降级错误信息。
- `frontend/src/api/message.ts`：WebSocket/SSE 事件分发；支持后端 `message:new` 真实卡片事件，并保留 tool_result fallback。
