# AgentHub 事件协议文档

## 概述

AgentHub 后端采用单层事件总线设计：

- **`EventDispatcher`**（`agent_runtime.runtime.event_dispatcher`）：运行时事件分发器，按类型过滤并分发到多个 Sink
- **`EventSink`**（`agent_runtime.core.interfaces`）：事件接收接口，由 app 层实现
- **`SSEEventSink`**（`app.events.sse_sink`）：EventSink 的 SSE 实现，负责把事件送入 SSE 队列

所有事件统一通过 `Session` 的 `EventDispatcher` 分发，API 层只消费 SSE 队列。

---

## SSE 端点

```
POST /api/v1/conversations/{conversation_id}/stream
```

返回 `text/event-stream`，读取 `SSEEventSink` 的队列。

---

## 核心接口

### EventSink（agent_runtime 核心接口）

```python
class EventSink(ABC):
    @abstractmethod
    async def emit(self, event: Event) -> None: ...

    @abstractmethod
    async def emit_batch(self, events: List[Event]) -> None: ...
```

### EventDispatcher（事件分发器）

```python
class EventDispatcher:
    def register_sink(self, sink: EventSink, event_filter=None) -> EventDispatcher
    def unregister_sink(self, sink: EventSink) -> None
    async def dispatch(self, event: Event) -> None
    async def dispatch_batch(self, events: List[Event]) -> None
```

`event_filter` 支持：
- `None`：接收所有事件
- `str`（通配符）：如 `"agent.*"`、`"system.*"`
- `Callable[[Event], bool]`：自定义过滤函数

---

## SSEEventSink

`SSEEventSink` 实现 `EventSink` 接口，每个会话维护一个 `asyncio.Queue`。

### 事件路由流程

```
Orchestrator.run() → Session.run() → EventDispatcher → SSEEventSink
                                                               ↓
                                                           asyncio.Queue
                                                               ↓
                                               SSE /stream 端点读取 → 前端
```

### 获取队列

```python
queue = SSEEventSink.get_queue_for(conversation_id)
```

---

## 应用层事件（EventBus - 遗留）

旧的 `EventBus`（`app.services.events`）是业务层事件总线，与运行时事件无关：

- 用于发布**业务层事件**（消息变更、任务状态等）
- `EventBus.publish(channel, event_name, data)` 直接推入 SSE 端点
- 与 `SSEEventSink` 的 Queue 并存，但路径不同

**建议**：业务层事件也应统一走 `SSEEventSink`，而非另起炉灶。

---

## 事件类型

### 运行时事件（EventDispatcher 分发）

| type | 含义 | 典型 data |
|------|------|-----------|
| `control.*` | 控制事件（调度决策、看门狗等） |
| `agent.*` | Agent 观测事件（thinking、token、tool_call 等） |
| `user.*` | 用户相关事件（输入、等待输入等） |
| `system.*` | 系统级事件（session/round 生命周期等） |

### 业务层事件（EventBus.publish）

| 事件名 | 含义 | 典型 data |
|--------|------|-----------|
| `message:new` | 新消息创建 | Message 字典 |
| `message:updated` | 消息内容更新 | `{"id": "...", "updated_fields": [...]}` |
| `message_start` | Agent 消息流开始 | `{"agent_message_id": "...", "agent_id": "..."}` |
| `content_block_delta` | 流式文本片段 | `{"agent_message_id": "...", "delta": {"type": "text_delta", "text": "..."}}` |
| `message_stop` | Agent 消息流结束 | `{"agent_message_id": "...", "stop_reason": "end_turn"}` |
| `task:status_changed` | 任务状态变更 | Task 字典 |
| `task:subtask_updated` | 子任务状态变更 | Subtask 字典 |
| `workflow:run_updated` | Workflow 运行状态更新 | `{"run_id": "...", "status": "running", "progress": 30}` |
| `tool:started` | 工具开始执行 | `{"agent_id": "...", "tool_name": "...", "status": "running"}` |
| `tool:finished` | 工具执行完成 | `{"agent_name": "...", "tool_name": "...", "status": "success"}` |
| `orchestrator:error` | 编排器异常 | `{"error": "...", "error_type": "RuntimeError"}` |
| `generation:cancelled` | 生成被用户取消 | `{"conversation_id": "...", "cancelled": true}` |

---

## SSEEventSink 与 EventBus 的关系

| | SSEEventSink | EventBus（遗留） |
|--|--|--|
| 来源 | agent_runtime 运行时 | app 业务层 |
| 注入方式 | `Session.create(event_sink=...)` | 直接 `event_bus.publish()` |
| 队列 | `SSEEventSink._queues[conversation_id]` | `EventBus._queues[channel]` |
| SSE 消费 | `event_bus.subscribe()`（但实际读的是 EventBus 队列） | 是 |

**当前问题**：`SSEEventSink` 写了队列，但 SSE 端点实际读的是 `EventBus` 的队列，两者未统一。

---

## 前端订阅示例

```javascript
const es = new EventSource(`/api/v1/conversations/${id}/stream`, {
  method: 'POST',
  body: JSON.stringify(payload),
  headers: { 'Content-Type': 'application/json' }
});

es.addEventListener('message:new', (e) => {
  const data = JSON.parse(e.data);
});

es.addEventListener('content_block_delta', (e) => {
  const data = JSON.parse(e.data);
  appendText(data.delta.text);
});

es.addEventListener('message_stop', (e) => {
  const data = JSON.parse(e.data);
  finalizeMessage(data.agent_message_id, data.stop_reason);
});
```

---

## Redis 集成（EventBus 遗留）

`EventBus` 使用 Redis 作为可选的跨进程消息总线（`app.services.events`）：

- `publish(channel, payload)` → Redis pub/sub
- `xadd(stream:{channel}, ...)` → Redis stream 历史

本地开发无 Redis 时自动降级，仅走内存队列。