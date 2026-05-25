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

## 后端入口

- `backend/app/main.py`：FastAPI 应用入口，注册 CORS、异常处理、健康检查和所有 API 路由。
- `backend/main.py`：兼容启动入口，转发到 `app.main`。
- `backend/alembic.ini`：Alembic 配置。
- `backend/alembic/env.py`：迁移运行环境，读取 SQLAlchemy metadata。
- `backend/alembic/versions/*.py`：数据库迁移脚本。
- `backend/pyproject.toml`：后端项目元数据、运行依赖和开发依赖。
- `backend/uv.lock`：uv 锁文件，保证依赖解析可复现。
- `backend/.python-version`：uv 使用的 Python 版本约束。

## 后端 core

- `backend/app/core/config.py`：统一配置。当前只读取项目根目录 `.env` 和 `backend/.env`，不读取项目外层目录。
- `backend/app/core/database.py`：SQLAlchemy engine、session、SQLite 兼容配置。
- `backend/app/core/security.py`：密码哈希、JWT 创建和解析。
- `backend/app/core/errors.py`：业务异常类型。
- `backend/app/core/response.py`：统一响应结构。

## 后端模型

所有主要数据库表定义在 `backend/app/models.py`。

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

- `backend/app/api/auth.py`：注册、登录、演示登录、当前用户、修改资料、改密码。
- `backend/app/api/workspaces.py`：工作区、成员、项目文件、提示词模板、快捷命令。
- `backend/app/api/conversations.py`：会话创建、编辑、分类、归档、删除、成员、工作流画布、工作流运行态。
- `backend/app/api/messages.py`：消息列表、发送、重试、回复、SSE 流、停止生成。
- `backend/app/api/tasks.py`：后台任务、任务状态、取消、重试、子任务审批。
- `backend/app/api/agents.py`：Agent 广场、创建、AI 生成、编辑、删除、测试、能力解析。
- `backend/app/api/models.py`：模型供应商、模型配置、模型测试。
- `backend/app/api/files.py`：文件上传、列表、下载、提取文本、预览、摘要、向量入口、转换、删除。
- `backend/app/api/artifacts.py`：产物创建、获取、预览、保存版本、Diff、导出、兼容附件接口、知识库兼容接口。
- `backend/app/api/knowledge.py`：知识库、文档导入、上传和检索。
- `backend/app/api/skills.py`：Skill 创建、AI 生成、MCP 导入、测试、删除。
- `backend/app/api/mcp.py`：MCP 注册、导入、更新、探测、工具列表、工具调用、调用记录、删除。
- `backend/app/api/tools.py`：工具目录、创建工具、AI 生成工具、编辑、删除、调用。
- `backend/app/api/sandbox.py`：沙箱和远程连接管理。
- `backend/app/api/deployments.py`：部署预览、部署记录、回滚。
- `backend/app/api/security_ops.py`：审计日志、角色、权限、用户权限后台。
- `backend/app/api/context.py`：上下文接口。
- `backend/app/api/websocket.py`：WebSocket 连接入口。

## 后端 services

- `backend/app/services/chat/orchestrator.py`：核心编排服务。负责单聊/群聊入口、工作流执行、任务拆解、运行态同步、产物卡片生成。
- `backend/app/services/workflows/engine.py`：Dify 风格工作流执行入口，按画布节点和边调度执行。
- `backend/app/services/workflows/graph.py`：WorkflowGraph、Node、Edge、拓扑排序、并行层级和分支路径。
- `backend/app/services/workflows/nodes/`：start、agent、tool、skill、mcp、condition、loop、review、artifact、end 节点执行器。
- `backend/app/services/workflows/runtime.py`：WorkflowRun/NodeRun/EdgeRun JSON 运行态持久化和会话同步。
- `backend/app/services/workflows/validator.py`：节点配置、边、权限引用、循环上限和 DAG 校验。
- `backend/app/services/agents/function_loop.py`：单聊和群聊共用的 Agent Function Call Loop，负责 tool_calls、role=tool 回填和最终回复。
- `backend/app/services/agents/tool_loop.py`：工具 schema 构造，以及 Tool、Skill、MCP 执行分发。
- `backend/app/services/ark.py`：火山方舟和 OpenAI-compatible 模型适配，包括普通调用、流式调用和 mock fallback。
- `backend/app/services/llm_gateway.py`：模型配置测试和模型调用统一入口。
- `backend/app/services/tools/registry.py`：内置工具目录、官方 Agent 工具箱、自定义工具调用、工具权限归一化。
- `backend/app/services/file_tools.py`：文件解析、预览、摘要、向量入口、PDF/DOCX/XLSX/PPTX/HTML/Markdown/ZIP 生成和转换。
- `backend/app/services/files.py`：上传文件落盘、路径计算、安全文件名。
- `backend/app/services/artifacts.py`：产物对象创建和基础内容组织。
- `backend/app/services/artifact_exports.py`：产物导出为不同格式。
- `backend/app/services/mcp_runtime.py`：HTTP/stdio MCP 调用、超时、环境变量过滤、调用记录。
- `backend/app/services/knowledge.py`：轻量知识库切片、索引、检索和上下文片段构造。
- `backend/app/services/realtime/event_bus.py`：事件总线，优先 Redis PubSub，缺省使用内存队列；用于 SSE/实时状态。
- `backend/app/services/queue.py`：后台任务队列，优先 Redis，缺省使用内存队列。
- `backend/app/services/audit.py`：权限判断和审计日志写入。
- `backend/app/services/serialization.py`：后端模型转前端 JSON，负责敏感字段脱敏。
- `backend/app/services/output_filter.py`：过滤内部任务拆解、执行过程、审查草稿等不该直接展示给用户的文本。
- `backend/app/services/seed.py`：初始化演示用户、工作区、官方 Agent、模型、角色、权限和基础数据。

## 后端 schemas

- `backend/app/schemas/common.py`：通用 schema。
- `backend/app/schemas/requests.py`：请求体 schema，覆盖 Agent、模型、工具、Skill、MCP 等创建和测试请求。

## 前端入口

- `frontend/src/main.tsx`：React 应用挂载入口。
- `frontend/src/App.tsx`：当前前端主文件，包含登录页、工作台、会话列表、聊天区、Agent 广场、成员管理、会话设置、工作流画布、全局设置、平台控制、产物预览等组件。
- `frontend/src/api.ts`：前端 API SDK，统一封装 token、请求、fallback、SSE 流、文件下载和 mock 数据兜底。
- `frontend/src/types.ts`：前端领域类型定义。
- `frontend/src/styles.css`：布局、IM 工作台、消息、侧边栏、画布、抽屉、产物预览等样式。
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
- `PreviewPanel`：产物预览、编辑、Diff、导出。
- `BackgroundTasksButton`：后台任务入口。

## 测试文件

- `tests/conftest.py`：后端测试 fixture，创建测试数据库和 FastAPI client。
- `tests/test_auth.py`：注册、登录、演示用户。
- `tests/test_auth_settings.py`：用户资料和密码设置。
- `tests/test_conversation.py`：会话、成员、分类、工作流。
- `tests/test_message.py`：消息发送、流式、附件。
- `tests/test_orchestrator.py`：多 Agent 编排和工作流运行。
- `tests/test_orchestrator_output.py`：输出过滤和最终回复。
- `tests/test_artifact.py`：产物创建、版本、Diff、预览。
- `tests/test_deployment.py`：部署记录。
- `tests/test_tools_files.py`：文件工具和工具目录。
- `tests/test_skills.py`：Skill 创建、测试、删除。
- `tests/test_model_mcp_sandbox.py`：模型、MCP、沙箱。
- `tests/test_platform_extensions.py`：平台扩展能力。
- `tests/test_workspace_security_deploy_task.py`：工作区、权限、部署、后台任务。
- `frontend/tests/app-render.test.tsx`：前端基础渲染测试。
- `e2e/agenthub-demo.spec.ts`：端到端演示链路。

## 运行数据目录

- `var/storage/uploads`：本地上传文件。
- `var/ai-tools/generated`：AI 生成或用户创建的 Python 工具片段。
- `var/backend.log`、`var/backend.err.log`：后端运行日志。
- `var/frontend.log`、`var/frontend.err.log`：前端运行日志。

`var` 是本地运行数据目录，里面的内容不属于核心源码。
