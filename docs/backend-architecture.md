# AgentHub 后端架构概览

## 一、总体架构

AgentHub 后端采用经典的分层架构，自上而下分为六层：

```
┌─────────────────────────────────────────────────────────────┐
│  API 层 (app/api/)                                           │
│  - RESTful HTTP API                                          │
│  - WebSocket 实时对话端点                                     │
│  - SSE 流式接口（兼容路径）                                   │
├─────────────────────────────────────────────────────────────┤
│  应用服务层 (app/services/)                                   │
│  - 业务编排与协调                                            │
│  - 工具注册表与执行                                          │
│  - Conversation 会话管理                                      │
├─────────────────────────────────────────────────────────────┤
│  运行时层 (agent_runtime/)                                    │
│  - 多智能体会话引擎（Session / Orchestrator）                 │
│  - Agent 执行循环（AgentLoop）                                │
│  - 调度策略（Scheduler）                                      │
│  - 事件分发（EventDispatcher）                                │
├─────────────────────────────────────────────────────────────┤
│  模型提供层 (model_provider/)                                 │
│  - 统一 LLM 调用接口                                          │
│  - 多供应商适配（Ark / OpenAI Compatible）                    │
├─────────────────────────────────────────────────────────────┤
│  持久化层 (app/persistence/, app/models/)                     │
│  - SQLAlchemy ORM 数据模型                                    │
│  - 异步数据库访问                                            │
├─────────────────────────────────────────────────────────────┤
│  基础设施层 (common/, app/core/)                              │
│  - 日志、配置、安全、数据库连接池                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、各层详解

### 2.1 API 层 (`app/api/`)

负责接收前端请求、认证授权、参数校验，并将请求转发到应用服务层。

| 模块 | 职责 |
|------|------|
| `websocket.py` | WebSocket 异步对话端点 (`/ws/conversations/{id}`)，支持双向实时通信、心跳保活、generation 取消 |
| `messages.py` | SSE 流式接口 (`/conversations/{id}/stream`)，兼容路径，内部委托给运行时层 |
| `conversations.py` | 会话 CRUD、参与者管理 |
| `agents.py` | Agent CRUD、能力管理 |
| `auth.py` | 登录、注册、Token 签发与校验 |
| `files.py` / `artifacts.py` | 文件上传、产物管理 |
| `tools.py` / `mcp.py` / `skills.py` | 工具、MCP 服务、Skill 的管理接口 |
| `models.py` | 模型供应商与模型配置管理 |

**关键设计**：
- WebSocket 是主推的实时通信协议，SSE 保留用于向后兼容
- API 层不直接调用 LLM，所有智能体相关操作委托给 `agent_runtime`

---

### 2.2 应用服务层 (`app/services/`)

承载核心业务逻辑，是 API 层与运行时层之间的桥梁。

| 模块 | 职责 |
|------|------|
| `conversation_session_manager.py` | **Conversation 级会话管理器**（进程内单例）。管理每个 conversation 的长期运行 `AgentSession`，负责创建/复用、用户输入发送、generation 取消、Session 清理 |
| `runtime_service.py` | **统一编排入口**。根据 Agent 数量自动选择调度器（单 Agent → `SingleAgentScheduler`，多 Agent → `TechLeadScheduler`），创建 `AgentSession` |
| `runtime_adapter.py` | **适配器层**。将 `agent_runtime` 的 `ToolExecutor` 接口桥接到 app 层的 `build_tools_for_agent` / `execute_tool_by_name` |
| `agentic_runtime.py` | 旧版工具注册与执行系统，被 `runtime_adapter.py` 复用 |
| `tool_registry.py` | 工具定义注册表 |
| `orchestrator.py` | 旧版编排器（正在逐步迁移到 `agent_runtime`） |
| `llm_gateway.py` / `ark.py` | LLM 调用网关（旧版兼容） |
| `artifacts.py` / `file_tools.py` | 产物与文件相关业务逻辑 |
| `mcp_runtime.py` | MCP 工具运行时管理 |

**关键设计**：
- `ConversationSessionManager` 是进程内单例，多进程部署时需配合 sticky session
- `OrchestratorService.create_session()` 是创建 `AgentSession` 的唯一入口

---

### 2.3 运行时层 (`agent_runtime/`)

纯 Python 实现的多智能体会话引擎，零框架依赖，通过接口注入外部依赖。

```
agent_runtime/
├── core/
│   ├── interfaces.py      # 抽象接口：PersistenceBackend, EventSink, ToolExecutor
│   └── types.py           # 核心数据类型：Event, Message, AgentConfig, ToolCall, ToolResult
├── runtime/
│   ├── session.py         # Session：用户入口，管理 EventDispatcher 生命周期
│   ├── orchestrator.py    # Orchestrator：会话级调度循环
│   ├── agent_loop.py      # AgentLoop：单 Agent 单轮执行循环
│   ├── event_dispatcher.py # EventDispatcher：多 Sink 并发事件分发
│   └── watchdog.py        # Watchdog：看门狗硬规则校验
├── strategies/
│   ├── base.py            # Scheduler 基类
│   ├── single_agent.py    # 单 Agent 调度器（纯代码，无 LLM 开销）
│   ├── tech_lead.py       # TechLead 调度器（LLM 驱动协调）
│   └── workflow.py        # 工作流调度器
├── context/
│   ├── blackboard.py      # BlackboardManager：全局共享上下文
│   └── agent_ctx.py       # AgentContextManager：私有上下文栈
└── tools/
    ├── registry.py        # ToolRegistry：工具注册表
    └── executor.py        # ToolExecutorImpl：工具执行器实现
```

**核心组件说明**：

#### Session (`runtime/session.py`)
- 用户使用 `agent_runtime` 的唯一入口
- 纯运行时对象，不依赖 HTTP、数据库或任何框架
- 通过 `EventDispatcher` 将事件并发分发给所有已注册的 Sink
- 支持 `run()` 启动会话和 `send_message()` 向运行中会话发送新消息

#### Orchestrator (`runtime/orchestrator.py`)
- 会话级调度循环，负责多轮调度
- 流程：初始化 → 收集 Agent 报告 → 看门狗校验 → 调度器决策 → 执行 → 归档 → 循环判断
- 支持用户中途输入（插队或完成后重启）

#### AgentLoop (`runtime/agent_loop.py`)
- 单 Agent 单轮执行循环
- 流程：构建上下文 → 调用 LLM（支持工具调用）→ 处理工具调用（多轮，最多 10 轮）→ 解析回复 → 归档
- 支持流式模式（emit `agent.token` 事件）

#### EventDispatcher (`runtime/event_dispatcher.py`)
- 运行时唯一事件总线
- 支持多 Sink 并发消费，支持按事件类型过滤（通配符或自定义函数）
- 各 Sink 由 app 层注册到 Session

---

### 2.4 模型提供层 (`model_provider/`)

统一 LLM 调用接口，屏蔽不同供应商的差异。

```
model_provider/
├── core/
│   ├── interfaces.py      # BaseModelProvider 接口（chat / chat_stream）
│   └── config.py          # ModelConfig 配置
├── providers/
│   └── ark.py             # 火山方舟（Ark）Provider 实现
└── factory.py             # create_provider() 工厂函数
```

**接口设计**：
- `chat()`：非流式对话，返回 `ChatResponse`
- `chat_stream()`：流式对话，返回 `AsyncIterator[StreamChunk]`
- 支持 tools（Function Calling）、system_prompt、temperature、max_tokens 等参数

---

### 2.5 持久化层 (`app/models.py`, `app/persistence/`)

#### 数据模型 (`app/models.py`)

核心实体：

| 实体 | 说明 |
|------|------|
| `User` / `UserSettings` | 用户与偏好设置 |
| `Workspace` / `WorkspaceMember` | 工作区与成员 |
| `Project` / `ProjectFile` | 项目与文件快照 |
| `Agent` / `AgentCapability` | 智能体与能力 |
| `Conversation` / `ConversationParticipant` | 会话与参与者 |
| `Message` / `MessageVersion` | 消息与版本历史 |
| `Task` / `Subtask` / `TaskDependency` | 任务与子任务 |
| `Artifact` / `ArtifactVersion` | 产物与版本 |
| `ToolDefinition` | 工具定义 |
| `Skill` | Skill 定义 |
| `ModelProvider` / `ModelConfig` | 模型供应商与配置 |
| `McpServer` / `McpToolInvocation` | MCP 服务与调用记录 |
| `SandboxSession` / `RemoteConnection` | 沙箱与远程连接 |
| `KnowledgeBase` / `KnowledgeDocument` | 知识库与文档 |
| `AuditLog` | 审计日志 |

#### 持久化后端实现 (`app/persistence/sqlalchemy_backend.py`)

实现 `agent_runtime.core.interfaces.PersistenceBackend` 接口，将运行时抽象桥接到 SQLAlchemy ORM：
- `create_conversation()` / `load_messages()` / `save_message()`
- `load_blackboard()` / `save_blackboard()`（基于 `Conversation.extra`）
- `load_agent_context()` / `save_agent_context()`（基于 `Conversation.extra`）

---

### 2.6 基础设施层 (`common/`, `app/core/`)

| 模块 | 职责 |
|------|------|
| `common/logger.py` | 结构化日志（基于 `structlog`） |
| `app/core/config.py` | 应用配置（Pydantic Settings） |
| `app/core/database.py` | 异步数据库引擎与 Session 依赖 |
| `app/core/security.py` | JWT Token 签发与校验、密码哈希 |
| `app/core/errors.py` | 统一异常体系 |
| `app/core/response.py` | 统一响应封装 |

---

## 三、数据流

### 3.1 对话请求流（WebSocket 路径）

```
前端 WebSocket
    │  {"event": "chat.send", "data": {...}}
    ▼
websocket.py:conversation_websocket()
    │
    ├── _authenticate_ws() ──► 用户认证
    ├── _save_user_message() ──► 保存用户消息到 DB
    │
    ▼
ConversationSessionManager.get_or_create_session()
    │  获取或创建 AgentSession（第一次创建，后续复用）
    ▼
OrchestratorService.create_session()
    │  创建 Session + EventDispatcher + 注册 WebSocketSink
    ▼
session_manager.send_user_input()
    │  运行中：插队 / 已完成：重启 generation
    ▼
AgentSession.run() / send_message()
    │
    ├── Orchestrator.run() ──► 调度循环
    │   ├── BlackboardManager ──► 全局上下文
    │   ├── AgentContextManager ──► 私有上下文
    │   ├── Scheduler.make_decision() ──► 调度决策
    │   ├── Watchdog.check_*() ──► 看门狗校验
    │   └── AgentLoop.run() ──► Agent 执行
    │       ├── ModelProvider.chat_stream() ──► LLM 调用
    │       └── ToolExecutor.execute() ──► 工具执行
    │
    └── EventDispatcher.dispatch(event)
        │
        ├──► WebSocketSink.emit() ──► 推送到前端 WS
        ├──► SseSink.emit() ──► SSE 队列（兼容）
        └──► RedisSink.emit() ──► Redis pub/sub（跨进程）
```

### 3.2 事件分发流

```
AgentLoop / Orchestrator 生成 Event
    │
    ▼
EventDispatcher.dispatch(event)
    │
    ├── 匹配过滤条件 ──► _SinkEntry.matches()
    │
    ├──► WebSocketSink.emit()
    │       └── 遍历该 conversation 的所有 WebSocket 连接发送 JSON
    │
    ├──► SseSink.emit()
    │       └── 写入 asyncio.Queue，API 层读取推送 SSE
    │
    └──► RedisSink.emit()
            └── 发布到 Redis pub/sub + Stream（跨进程）
```

---

## 四、关键设计决策

### 4.1 双事件总线设计

| 维度 | 运行时事件总线 (EventDispatcher) | 业务层事件总线 (AppEventBus) |
|------|----------------------------------|------------------------------|
| 位置 | `agent_runtime` 内部 | `app/events/__init__.py` |
| 用途 | Agent 执行过程中的实时观测事件 | 业务状态变更通知（消息、任务等） |
| 典型事件 | `agent.token`, `system.agent_started` | `message:new`, `generation:cancelled` |
| 传输方式 | Sink 插件化（WebSocket / SSE / Redis） | asyncio.Queue + Redis pub/sub |
| 生产者 | AgentLoop, Orchestrator | 应用服务层（messages.py 等） |

### 4.2 调度策略自动选择

`OrchestratorService` 根据 conversation 中的 Agent 数量自动选择调度器：

- **单 Agent**：`SingleAgentScheduler` —— 纯代码，无 LLM 开销，直接执行
- **多 Agent**：`TechLeadScheduler` —— LLM 驱动的协调调度，模拟技术团队 Leader 的调度风格

### 4.3 上下文隔离：Blackboard + Agent Context

| 上下文类型 | 作用域 | 内容 | 可见性 |
|-----------|--------|------|--------|
| **Blackboard**（全局） | 会话级，所有 Agent 共享 | 历史记录、结构化摘要、KV 状态 | 前端用户可见 |
| **Agent Context**（私有） | Agent 级，每个 Agent 独立 | 系统提示词、思维链、工具调用草稿 | 前端用户默认不可见 |

### 4.4 适配器模式：运行时与业务层解耦

`ToolExecutorAdapter`（`runtime_adapter.py`）和 `_ToolExecutorAdapter`（`runtime_service.py`）实现 `agent_runtime.core.interfaces.ToolExecutor` 接口，内部将调用转发到 app 层的 `execute_tool_by_name`。这种设计使得：
- `agent_runtime` 保持纯运行时，不依赖业务层代码
- 业务层工具注册表无需改动即可被运行时复用

### 4.5 Session 生命周期管理

- `ConversationSessionManager` 以 conversation_id 为键缓存 `AgentSession`
- 首次消息时创建 Session，后续消息复用同一 Session
- Session 完成后不立即销毁，用户发送新消息时自动重启 generation
- 客户端断开 WebSocket 不影响 Session 继续运行

---

## 五、模块依赖关系

```
app/api/
    ├──► app/services/（业务编排）
    │       ├──► agent_runtime/（运行时引擎）
    │       │       ├──► model_provider/（LLM 调用）
    │       │       └──► app/persistence/（持久化接口实现）
    │       └──► app/models/（数据模型）
    └──► app/events/（事件 Sink）
            └──► agent_runtime/core/interfaces.py（EventSink 接口）

agent_runtime/（零业务依赖）
    ├──► model_provider/（通过接口注入）
    └──► app/persistence/（通过 PersistenceBackend 接口注入）
```

---

## 六、技术栈

| 领域 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| ORM | SQLAlchemy 2.0（异步） |
| 数据库迁移 | Alembic |
| 模型调用 | 火山方舟（Ark）/ OpenAI Compatible |
| 缓存/消息 | Redis（可选，跨进程事件） |
| 日志 | structlog |
| 配置 | Pydantic Settings |
| 测试 | pytest + pytest-asyncio |
| 代码规范 | Ruff |
