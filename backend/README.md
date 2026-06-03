# AgentHub 后端

基于 FastAPI + SQLAlchemy (async) 构建的多智能体协作平台后端。

## 技术栈

- **Python 3.11**
- **FastAPI** — Web 框架
- **SQLAlchemy 2.0 (async)** — ORM
- **Alembic** — 数据库迁移
- **Pydantic** — 数据校验与配置
- **uv** — 包管理与虚拟环境

## 目录结构

```
backend/
├── alembic/                # 数据库迁移脚本
├── src/
│   ├── app/                # FastAPI 应用层
│   │   ├── api/            # API 路由（按领域拆分）
│   │   ├── core/           # 核心配置、安全、异常、响应
│   │   ├── events/         # SSE 事件推送
│   │   ├── persistence/    # 运行时持久化适配
│   │   ├── schemas/        # Pydantic 请求/响应模型
│   │   └── services/       # 业务服务层
│   ├── db/                 # 数据库层（零依赖上层）
│   │   ├── models/         # 按领域拆分的 ORM 模型
│   │   ├── base.py         # DeclarativeBase、Mixin
│   │   ├── config.py       # 数据库配置
│   │   └── session.py      # 异步引擎与 Session
│   ├── agent_runtime/      # 多智能体运行时引擎
│   │   ├── core/           # 抽象接口与核心类型
│   │   ├── runtime/        # Session、Orchestrator、AgentLoop
│   │   ├── strategies/     # 调度器策略
│   │   ├── workflow/       # 工作流图遍历
│   │   ├── context/        # 黑板与 Agent 上下文
│   │   └── tools/          # 工具注册与执行
│   ├── model_provider/     # 大模型提供者抽象
│   │   ├── core/           # 接口与配置
│   │   └── providers/      # 具体实现（火山方舟等）
│   └── common/             # 共享工具
├── tests/                  # pytest 测试套件
├── pyproject.toml          # 项目配置与依赖
└── uv.lock                 # 依赖锁定文件
```

## 各模块职责

### `app/api/` — API 路由层

按业务领域拆分的 FastAPI 路由模块：

| 模块 | 职责 |
|------|------|
| `auth.py` | 注册、登录、演示登录、用户信息、修改密码 |
| `agents.py` | Agent 广场、创建、编辑、测试、删除 |
| `conversations.py` | 会话管理、成员、工作流画布、分类归档 |
| `messages.py` | 消息发送、流式响应、重试、停止生成 |
| `artifacts.py` | 产物创建、版本、Diff、预览、导出 |
| `files.py` | 文件上传、下载、解析、预览 |
| `workspaces.py` | 工作区、成员、项目文件、提示词模板 |
| `models.py` | 模型供应商配置、模型列表、测试 |
| `skills.py` | Skill 创建、AI 生成、测试、删除 |
| `tools.py` | 工具目录、自定义工具、AI 生成工具 |
| `mcp.py` | MCP 服务注册、探测、调用、记录 |
| `sandbox.py` | 沙箱会话、远程连接管理 |
| `deployments.py` | 部署预览、记录、回滚 |
| `security_ops.py` | 审计日志、角色权限管理 |
| `websocket.py` | WebSocket 实时连接 |

### `app/core/` — 应用核心

| 模块 | 职责 |
|------|------|
| `config.py` | 业务配置：密钥、模型参数、存储路径等 |
| `security.py` | JWT 签发/校验、密码哈希 |
| `errors.py` | 统一业务异常体系 |
| `response.py` | `ApiResponse[T]` 统一响应封装 |
| `logging_config.py` | 结构化日志配置 |

### `app/services/` — 业务服务层

| 模块 | 职责 |
|------|------|
| `runtime_service.py` | **统一编排入口**。根据 Agent 数量和会话配置选择调度策略，创建 `AgentSession` |
| `conversation_session_manager.py` | 会话生命周期管理，AgentSession 的进程内缓存与复用 |
| `agentic_runtime.py` | Agent 小循环：按权限选择并执行工具、Skill、MCP |
| `tool_registry.py` | 内置工具目录、权限归一化、自定义工具调用 |
| `file_tools.py` | 文件解析、预览、摘要、格式转换、向量入口 |
| `artifacts.py` / `artifact_exports.py` | 产物对象管理与多格式导出 |
| `mcp_runtime.py` | HTTP/stdio MCP 调用、超时控制、调用记录 |
| `knowledge.py` | 轻量知识库切片、索引、检索 |
| `llm_gateway.py` | 模型调用统一入口与配置测试 |
| `ark.py` | 火山方舟/OpenAI-compatible 模型适配 |
| `output_filter.py` | 过滤内部规划、任务拆解等不应展示给用户的内容 |
| `serialization.py` | 模型转前端 JSON，敏感字段脱敏 |
| `seed.py` | 初始化演示用户、官方 Agent、模型、角色权限 |
| `audit.py` | 权限判断与审计日志写入 |

### `db/` — 数据库层

**设计原则：零依赖上层**。`db/` 不 import `app.*` 或 `agent_runtime.*`。

| 模块 | 职责 |
|------|------|
| `base.py` | `DeclarativeBase`、`TimestampMixin`、`uuid_str()`、`utcnow` |
| `config.py` | 数据库配置：`database_url`、`resolved_database_url` |
| `session.py` | 异步引擎 `async_engine`、`AsyncSessionLocal`、`get_db()` |
| `models/users.py` | `User`、`UserSettings` |
| `models/workspaces.py` | `Workspace`、`WorkspaceMember`、`Project`、`ProjectFile`、`PromptTemplate`、`ShortcutCommand` |
| `models/agents.py` | `Agent`、`AgentCapability` |
| `models/conversations.py` | `Conversation`、`ConversationParticipant`、`Message`、`MessageVersion` |
| `models/workflows.py` | `WorkflowRun` |
| `models/tasks.py` | `Task`、`Subtask`、`TaskDependency` |
| `models/artifacts.py` | `Artifact`、`ArtifactVersion`、`Deployment` |
| `models/files.py` | `FileAsset`、`KnowledgeBase`、`KnowledgeDocument` |
| `models/capabilities.py` | `Skill`、`SkillRun`、`ToolDefinition`、`ToolInvocation`、`ModelProvider`、`ModelConfig`、`McpServer`、`McpToolInvocation`、`SandboxSession`、`RemoteConnection` |
| `models/security.py` | `AuditLog`、`Role`、`Permission`、`UserRole`、`RolePermission` |

### `agent_runtime/` — 多智能体运行时引擎

纯 Python 实现，零框架依赖，通过接口注入外部依赖。

| 模块 | 职责 |
|------|------|
| `core/interfaces.py` | 抽象接口：`PersistenceBackend`、`EventSink`、`ToolExecutor` |
| `core/types.py` | 核心数据类型：`Event`、`Message`、`AgentConfig`、`ToolCall` |
| `runtime/session.py` | **用户入口**。管理 `EventDispatcher` 生命周期，支持 `run()` 和 `send_message()` |
| `runtime/orchestrator.py` | 会话级调度循环：初始化 -> 收集报告 -> 看门狗校验 -> 调度决策 -> 执行 -> 循环 |
| `runtime/agent_loop.py` | 单 Agent 单轮执行：构建上下文 -> 调用 LLM -> 工具调用 -> 解析回复 |
| `runtime/event_dispatcher.py` | 运行时唯一事件总线，多 Sink 并发分发 |
| `runtime/watchdog.py` | 看门狗硬规则校验 |
| `strategies/base.py` | `Scheduler` 基类 |
| `strategies/single_agent.py` | 单 Agent 纯代码调度（无 LLM 开销） |
| `strategies/tech_lead.py` | TechLead 调度器（LLM 驱动协调） |
| `strategies/workflow.py` | 工作流调度器（带环图遍历） |
| `workflow/graph.py` | 工作流图数据结构 |
| `workflow/scheduler.py` | 工作流节点调度执行 |
| `workflow/conditions.py` | 条件表达式求值 |
| `workflow/replanner.py` | workflow sanitize 与默认 workflow 生成 |
| `context/blackboard.py` | 全局共享上下文（Blackboard） |
| `context/agent_ctx.py` | Agent 私有上下文栈 |
| `tools/registry.py` | 运行时工具注册表 |
| `tools/executor.py` | 工具执行器实现 |

### `model_provider/` — 大模型提供者抽象

| 模块 | 职责 |
|------|------|
| `core/interfaces.py` | `BaseModelProvider`、`ChatMessage`、`ChatResponse`、`StreamChunk` |
| `core/config.py` | 模型配置 |
| `factory.py` | 根据配置创建对应 provider |
| `providers/ark.py` | 火山方舟适配 |

### `app/persistence/` — 持久化适配

| 模块 | 职责 |
|------|------|
| `sqlalchemy_backend.py` | 实现 `PersistenceBackend` 接口，将运行时事件桥接到 SQLAlchemy ORM |

## 快速开始

### 安装依赖

```powershell
uv sync --extra dev
```

### 配置环境变量

在项目根目录创建 `.env`：

```env
DATABASE_URL=sqlite:///./agenthub_dev.db
SECRET_KEY=your-secret-key
LLM_PROVIDER=ark
ARK_BASE_URL=...
ARK_ENDPOINT_ID=...
ARK_API_KEY=...
```

### 数据库迁移

```powershell
uv run alembic upgrade head
```

### 启动服务

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 运行测试

```powershell
uv run pytest -q
```

## 核心数据流

### 发送消息

```text
frontend
  -> POST /api/v1/messages
  -> app/api/messages.py
  -> runtime_service.run()
  -> AgentSession.run()
  -> Scheduler 决策 -> AgentLoop 执行
  -> EventDispatcher 发布事件
  -> SseSink / WebSocket 推送到前端
```

### 工作流群聊

```text
conversation.extra.workflow
  -> sanitize_workflow()
  -> WorkflowScheduler 图遍历
  -> 节点逐个执行（agent / tool / condition / loop）
  -> 最终 assistant message 入库
```

## 开发规范

- 单个函数不超过 100 行，单个文件不超过 500 行
- 代码符合 PEP8，通过 `ruff check` 检查
- 函数和类使用 Google 风格中文注释
- 所有功能必须附带 `tests/` 下的 pytest 测试
