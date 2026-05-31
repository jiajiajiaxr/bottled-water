# AgentHub 前后端事件传输协议参考

## 一、概述

AgentHub 使用**双事件系统**来分别处理不同层面的事件：

```
┌─────────────────────────────────────────────────────────────────┐
│                     运行时事件系统                               │
│  生产者：AgentLoop / Orchestrator                                │
│  分发器：EventDispatcher                                         │
│  消费者：WebSocketSink → 前端 WS                                  │
│          SseSink      → SSE 流（兼容路径）                        │
│          RedisSink    → Redis pub/sub（跨进程）                   │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                     业务层事件系统                               │
│  生产者：应用服务层（messages.py 等）                              │
│  分发器：AppEventBus                                             │
│  消费者：asyncio.Queue（进程内）+ Redis pub/sub（跨进程）          │
│  用途：消息状态变更、任务通知等                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、WebSocket 协议

WebSocket 是主推的实时通信协议，端点为：

```
WS /ws/conversations/{conversation_id}?token={jwt_token}
```

### 2.1 客户端 → 服务端事件

客户端发送 JSON 消息：

```json
{
  "event": "chat.send",
  "data": { ... },
  "request_id": "可选的请求追踪 ID"
}
```

| 事件名 | 含义 | `data` 字段 | 说明 |
|--------|------|------------|------|
| `chat.send` | 发送用户消息 | `content`, `content_type`, `attachments`, `model_config_id`, `thinking_enabled`, `scheduling_strategy` | 触发 Agent generation |
| `chat.cancel` | 取消当前 generation | — | 取消运行中的 Task，推送 `control.cancel` 事件 |
| `ping` | 心跳保活 | — | 服务端响应 `pong` |

#### `chat.send` 的 `data` 结构

```typescript
{
  content: {
    text: string;           // 消息文本
    attachments?: Array<{   // 附件（文件引用）
      file_id: string;
      filename: string;
      content_type: string;
      size: number;
    }>;
  };
  content_type?: string;     // 默认 "text"
  model_config_id?: string;  // 指定的模型配置 ID
  thinking_enabled?: boolean;// 是否启用思考过程展示
  scheduling_strategy?: string; // 调度策略（如 "tech_lead"）
  reply_to_message_id?: string; // 引用消息 ID
  client_message_id?: string;   // 客户端消息 ID（用于去重）
}
```

### 2.2 服务端 → 客户端事件

服务端推送 JSON 消息：

```json
{
  "event": "agent.token",
  "data": { "agent_id": "xxx", "token": "..." },
  "request_id": "对应客户端请求的 ID（如有）"
}
```

#### 控制类事件（服务端主动）

| 事件名 | 含义 | `data` 字段 | 触发时机 |
|--------|------|------------|---------|
| `chat.ack` | 消息已接收确认 | `message_id`, `content_preview` | 用户消息保存到数据库后 |
| `chat.cancelled` | 取消确认 | `cancelled: boolean` | 用户发送 `chat.cancel` 后 |
| `pong` | 心跳响应 | `{}` | 收到 `ping` 后 |
| `error` | 错误通知 | `message: string` | 发生异常时 |

#### 运行时事件（由 EventDispatcher 分发）

运行时事件通过 `WebSocketSink` 推送到该 conversation 的所有 WebSocket 连接。所有运行时事件的结构统一为：

```json
{
  "event": "事件类型名",
  "data": { ...事件负载... },
  "request_id": "关联请求 ID（如有）"
}
```

---

## 三、SSE 兼容路径

SSE 端点保留用于向后兼容：

```
POST /api/v1/conversations/{conversation_id}/stream
```

SSE 格式：

```
event: agent.token\n
data: {"agent_id": "...", "token": "..."}\n\n
```

> **注意**：SSE 路径内部同样使用 `EventDispatcher` 分发事件，只是通过 `SseSink` 而不是 `WebSocketSink` 投递。事件类型和负载与 WebSocket 路径完全一致。

---

## 四、运行时事件详细列表

运行时事件按 `type` 前缀分为四大类：

### 4.1 `system.*` — 系统级事件（Session / Round / Agent 生命周期）

| 事件类型 | 含义 | `payload` 字段 | 生产者 |
|----------|------|---------------|--------|
| `system.session_started` | Session 启动 | `session_id`, `agents: [{id, name, role}]` | Orchestrator |
| `system.session_completed` | Session 正常结束 | `session_id`, `rounds`, `watchdog_status` | Orchestrator |
| `system.session_error` | Session 异常终止 | `session_id`, `error`, `error_type` | Orchestrator |
| `system.round_started` | 新一轮调度开始 | `round`, `session_id`, `agent_reports: [{agent_id, state, will}]` | Orchestrator |
| `system.agent_started` | 某个 Agent 开始执行 | `round`, `agent_id`, `agent_name`, `task` | Orchestrator |
| `system.agent_completed` | 某个 Agent 执行完成 | `round`, `agent_id`, `agent_name`, `work_product`, `status_report: {state, will, confidence, rationale}` | Orchestrator |
| `system.agent_failed` | 某个 Agent 执行失败 | `round`, `agent_id`, `error` | Orchestrator |

#### `system.agent_started` 示例

```json
{
  "event": "system.agent_started",
  "data": {
    "round": 1,
    "agent_id": "coder",
    "agent_name": "程序员",
    "task": "实现用户登录功能"
  }
}
```

#### `system.agent_completed` 示例

```json
{
  "event": "system.agent_completed",
  "data": {
    "round": 1,
    "agent_id": "coder",
    "agent_name": "程序员",
    "work_product": "已完成登录接口的实现...",
    "status_report": {
      "state": "completed",
      "will": "complete",
      "confidence": 0.95,
      "rationale": "代码已编写并通过基础测试"
    }
  }
}
```

### 4.2 `agent.*` — Agent 观测事件（思考、Token、工具调用）

| 事件类型 | 含义 | `payload` 字段 | 生产者 | 前端处理 |
|----------|------|---------------|--------|---------|
| `agent.thinking` | Agent 开始思考 | `task`, `agent_id` | AgentLoop | 可展示思考动画 |
| `agent.token` | 流式文本片段（增量） | `agent_id`, `token` | AgentLoop | **追加到消息内容** |
| `agent.tool_call` | Agent 发起工具调用 | `agent_id`, `tool_count`, `tools: [name]` | AgentLoop | 展示工具调用指示器 |
| `agent.tool_result` | 工具执行结果 | `agent_id`, `tool`, `success` | AgentLoop | 更新工具调用状态 |
| `agent.tool_calls_executed` | 本轮所有工具调用完成汇总 | `agent_id`, `round`, `results: [{tool, success, result}]` | Orchestrator | 可展示工具调用历史 |

#### `agent.token` 示例

```json
{
  "event": "agent.token",
  "data": {
    "agent_id": "coder",
    "token": "首先，我们需要验证用户输入..."
  }
}
```

> `agent.token` 是**最核心的流式事件**，前端通过逐字追加实现"打字机效果"。

#### `agent.tool_call` 示例

```json
{
  "event": "agent.tool_call",
  "data": {
    "agent_id": "coder",
    "tool_count": 2,
    "tools": ["file_read", "file_write"]
  }
}
```

### 4.3 `control.*` — 控制事件（调度决策、看门狗）

| 事件类型 | 含义 | `payload` 字段 | 生产者 | 前端处理 |
|----------|------|---------------|--------|---------|
| `control.scheduling_decision` | 调度器做出决策 | `round`, `decision` (assign/parallel/wait/escalate/user_input/complete), `target`, `task`, `rationale` | TechLeadScheduler | 可展示调度决策面板 |
| `control.watchdog_triggered` | 看门狗触发干预 | 看门狗状态详情 | Watchdog | 通常不展示 |
| `control.escalation` | 任务升级（需人工介入） | `rationale`, `target` | Orchestrator | 提示用户介入 |
| `control.cancel` | Generation 被取消 | `conversation_id`, `reason` | ConversationSessionManager | **停止流式展示，标记消息为取消状态** |

#### `control.scheduling_decision` 示例

```json
{
  "event": "control.scheduling_decision",
  "data": {
    "round": 1,
    "decision": "assign",
    "target": "coder",
    "task": "实现用户登录接口",
    "rationale": "程序员 Agent 具备代码编写能力，当前状态为就绪"
  }
}
```

#### `control.cancel` 示例

```json
{
  "event": "control.cancel",
  "data": {
    "conversation_id": "conv-xxx",
    "reason": "user_cancelled"
  }
}
```

> `control.cancel` 通过 `WebSocketSink` 推送，前端收到后应立即停止当前流式消息的渲染，并允许用户发送新消息。

### 4.4 `user.*` — 用户相关事件

| 事件类型 | 含义 | `payload` 字段 | 生产者 |
|----------|------|---------------|--------|
| `user.input_received` | 用户中途输入已被接收 | `content` | Orchestrator |
| `user.input_queued` | 用户输入已放入队列 | `content` | Orchestrator |
| `user.waiting_for_input` | 调度器请求用户输入 | `rationale` | Orchestrator |

---

## 五、业务层事件详细列表

业务层事件通过 `AppEventBus.publish(channel, event, data)` 发布，主要用于业务状态变更通知。

### 5.1 消息类事件

| 事件名 | 含义 | `data` 字段 | 发布位置 |
|--------|------|------------|---------|
| `message:new` | 新消息创建（用户消息） | `Message` 字典（含 `id`, `content`, `sender_type` 等） | `messages.py` |
| `message:updated` | 消息内容更新 | `{"id": "...", "updated_fields": [...]}` | 消息编辑时 |
| `message_start` | Agent 消息流开始 | `{"agent_message_id": "...", "agent_id": "..."}` | 旧版兼容 |
| `content_block_delta` | 流式文本片段（旧版格式） | `{"agent_message_id": "...", "delta": {"type": "text_delta", "text": "..."}}` | 旧版兼容 |
| `message_stop` | Agent 消息流结束 | `{"agent_message_id": "...", "stop_reason": "end_turn"}` | 旧版兼容 |

### 5.2 任务与流程类事件

| 事件名 | 含义 | `data` 字段 | 发布位置 |
|--------|------|------------|---------|
| `task:status_changed` | 任务状态变更 | `Task` 字典 | 任务服务层 |
| `task:subtask_updated` | 子任务状态变更 | `Subtask` 字典 | 任务服务层 |
| `workflow:run_updated` | Workflow 运行状态更新 | `{"run_id": "...", "status": "running", "progress": 30}` | 工作流服务层 |

### 5.3 工具与编排类事件

| 事件名 | 含义 | `data` 字段 | 发布位置 |
|--------|------|------------|---------|
| `tool:started` | 工具开始执行 | `{"agent_id": "...", "tool_name": "...", "status": "running"}` | 工具执行前 |
| `tool:finished` | 工具执行完成 | `{"agent_name": "...", "tool_name": "...", "status": "success"}` | 工具执行后 |
| `orchestrator:error` | 编排器异常 | `{"error": "...", "error_type": "RuntimeError"}` | 编排异常时 |
| `generation:cancelled` | 生成被用户取消 | `{"conversation_id": "...", "cancelled": true}` | `messages.py:cancel_stream()` |

> **注意**：`generation:cancelled` 在 `messages.py:cancel_stream()` 中发布，但目前正在被迁移到 `control.cancel` 运行时事件。建议新代码监听 `control.cancel`。

---

## 六、前端事件处理映射

### 6.1 SSE 路径事件处理（`frontend/src/api/message.ts`）

```typescript
switch (event) {
  // Session 生命周期
  case "system.session_started":
  case "system.session_completed":
    // 忽略或记录日志
    break;

  case "system.session_error":
    // 结束流式，展示错误
    handlers.onDone?.(data);
    break;

  // Agent 生命周期
  case "system.agent_started":
    handlers.onMessageStart?.(data);  // 创建流式消息占位
    break;

  case "system.agent_completed":
  case "system.agent_failed":
    handlers.onMessageEnd?.(data);    // 归档到历史消息
    break;

  // 工具调用
  case "agent.tool_calls_executed":
    // 遍历 tool_events，调用 onToolCallStart / onToolCallDone
    break;

  // 流式内容
  case "agent.token":
    handlers.onToken?.(agentId, token);  // 追加文本
    break;

  case "agent.thinking":
    // 暂不处理
    break;

  // 控制类（暂不直接展示）
  case "control.watchdog_triggered":
  case "control.scheduling_decision":
  case "control.escalation":
  case "user.waiting_for_input":
  case "user.input_received":
  case "user.input_queued":
    break;
}
```

### 6.2 流式消息状态管理（`frontend/src/hooks/useStreamingMessages.ts`）

前端使用 `Map<string, ChatMessage>` 管理正在流式传输中的消息：

| Handler | 动作 |
|---------|------|
| `onMessageStart` | 在 `streamingMessages` Map 中创建占位消息（`streamState: "streaming"`），加入 `displayOrder` |
| `onToken` | 追加 token 到对应 agentId 的消息 `content`，递增版本号触发重新渲染 |
| `onMessageEnd` | 从 `streamingMessages` 移除，归档到历史消息数组（`streamState: "done"`） |
| `onDone` | 设置 `streamState: "done"` |

**状态流转**：

```
idle ──onMessageStart──► streaming ──onMessageEnd──► 归档到历史消息
                              │
                              └──onDone──► done
```

---

## 七、事件完整流向图

### 7.1 典型对话场景的事件流

```
用户发送消息
    │
    ├──► WS: chat.ack ──────────────────────────────► 前端：消息已确认
    │
    ▼
Orchestrator 启动
    │
    ├──► system.session_started ────────────────────► 前端：可展示会话开始提示
    │
    ├──► system.round_started ──────────────────────► 前端：展示第 N 轮开始
    │
    ├──► control.scheduling_decision ───────────────► 前端（可选）：展示调度决策
    │       decision=assign, target=coder
    │
    ├──► system.agent_started ──────────────────────► 前端：创建 coder 的流式消息占位
    │       agent_id=coder
    │
    ├──► agent.thinking ────────────────────────────► 前端（可选）：展示思考动画
    │
    ├──► agent.token ──► agent.token ──► ... ──────► 前端：逐字追加，打字机效果
    │       "首先..."      "我们需要..."
    │
    ├──► agent.tool_call ───────────────────────────► 前端：展示"正在调用工具..."
    │       tools=["file_read"]
    │
    ├──► agent.tool_result ─────────────────────────► 前端：更新工具调用状态为完成
    │       tool="file_read", success=true
    │
    ├──► agent.token ──► agent.token ──► ... ──────► 前端：继续追加文本
    │
    ├──► system.agent_completed ────────────────────► 前端：归档 coder 消息到历史
    │       work_product="...", status_report={...}
    │
    ├──► control.scheduling_decision ───────────────► 前端（可选）：下一轮决策
    │       decision=assign, target=reviewer
    │
    ├──► system.agent_started ──────────────────────► 前端：创建 reviewer 的流式消息占位
    │       agent_id=reviewer
    │
    ├──► agent.token ──► ... ──────────────────────► 前端：逐字追加
    │
    ├──► system.agent_completed ────────────────────► 前端：归档 reviewer 消息
    │
    └──► system.session_completed ──────────────────► 前端：会话结束，允许新输入
```

### 7.2 取消场景的事件流

```
用户点击"停止生成"
    │
    ├──► WS: chat.cancel ───────────────────────────► 服务端
    │
    ▼
ConversationSessionManager.cancel_generation()
    │
    ├──► 取消 asyncio.Task
    │
    └──► WS: control.cancel ────────────────────────► 前端：停止流式，标记取消
            data={"conversation_id": "...", "reason": "user_cancelled"}
```

---

## 八、事件类型速查表

### 8.1 运行时事件（按前缀分组）

| 前缀 | 类别 | 事件列表 |
|------|------|---------|
| `system.*` | 系统生命周期 | `session_started`, `session_completed`, `session_error`, `round_started`, `agent_started`, `agent_completed`, `agent_failed` |
| `agent.*` | Agent 观测 | `thinking`, `token`, `tool_call`, `tool_result`, `tool_calls_executed` |
| `control.*` | 控制与调度 | `scheduling_decision`, `watchdog_triggered`, `escalation`, `cancel` |
| `user.*` | 用户交互 | `input_received`, `input_queued`, `waiting_for_input` |

### 8.2 WebSocket 协议事件（客户端 ↔ 服务端）

| 方向 | 事件名 | 含义 |
|------|--------|------|
| C→S | `chat.send` | 发送消息 |
| C→S | `chat.cancel` | 取消生成 |
| C→S | `ping` | 心跳 |
| S→C | `chat.ack` | 消息确认 |
| S→C | `chat.cancelled` | 取消确认 |
| S→C | `pong` | 心跳响应 |
| S→C | `error` | 错误通知 |
| S→C | `system.*` | 系统生命周期事件 |
| S→C | `agent.*` | Agent 观测事件 |
| S→C | `control.*` | 控制事件 |
| S→C | `user.*` | 用户事件 |

### 8.3 业务层事件

| 事件名 | 类别 | 含义 |
|--------|------|------|
| `message:new` | 消息 | 新消息创建 |
| `message:updated` | 消息 | 消息更新 |
| `message_start` | 消息（旧版） | 流式开始 |
| `content_block_delta` | 消息（旧版） | 流式片段 |
| `message_stop` | 消息（旧版） | 流式结束 |
| `task:status_changed` | 任务 | 任务状态变更 |
| `task:subtask_updated` | 任务 | 子任务更新 |
| `workflow:run_updated` | 工作流 | 运行状态更新 |
| `tool:started` | 工具 | 工具开始 |
| `tool:finished` | 工具 | 工具完成 |
| `orchestrator:error` | 编排 | 编排异常 |
| `generation:cancelled` | 生成 | 生成被取消（逐步迁移到 `control.cancel`） |

---

## 九、开发注意事项

1. **事件类型命名规范**：运行时事件使用 `category.action` 格式（如 `agent.token`），业务层事件使用 `resource:action` 格式（如 `message:new`）。

2. **WebSocket 连接断开不影响 Session**：客户端断开 WS 后，`WebSocketSink` 仅停止向该连接推送，Session 和 generation 继续运行。客户端重连后可重新接收后续事件。

3. **多客户端同时在线**：同一 conversation 支持多个 WebSocket 连接同时在线（如 Web + 移动端），`WebSocketSink` 会向所有活跃连接广播事件。

4. **取消事件的双重路径**：
   - 新路径（推荐）：`chat.cancel` → `cancel_generation()` → `control.cancel` 运行时事件
   - 旧路径（兼容）：`POST /stream/cancel` → `generation:cancelled` 业务层事件
   前端应同时监听两者以确保兼容性。

5. **SSE 与 WebSocket 事件一致性**：两套路径使用相同的 `EventDispatcher` 和事件类型，只是 Sink 不同（`SseSink` vs `WebSocketSink`），事件负载完全一致。
