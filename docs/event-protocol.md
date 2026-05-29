# AgentHub 事件协议文档

## 架构

```
Orchestrator.run()
    ↓
Session.run()
    ↓
EventDispatcher（运行时事件总线）
    ├── SseSink      → 前端 SSE
    ├── RedisSink    → 跨进程 Redis pub/sub
    ├── DbSink       → 数据库持久化（可选）
    └── ...
```

- **EventDispatcher**：运行时唯一事件总线，在 `Session` 创建时通过 `register_sink` 注册多个 Sink
- **SseSink**：`EventSink` 实现，将事件写入 `asyncio.Queue`，API 层读取推送给前端
- **RedisSink**：`EventSink` 实现，将事件发布到 Redis pub/sub + Stream
- **AppEventBus**（`app_event_bus`）：业务层事件（消息变更、任务状态等）的发布订阅，非运行时

---

## 注册方式

```python
from agent_runtime import Session
from app.events import SseSink, RedisSink

session = Session.create(
    agents=agent_configs,
    scheduler=scheduler,
    model_provider=model_provider,
    event_sink=SseSink(conversation_id=str(conversation.id)),
    # 注册多个 Sink
)
```

运行时事件直接通过 `EventDispatcher.dispatch()` 分发给所有已注册的 Sink。

---

## SSE 端点

```
POST /api/v1/conversations/{conversation_id}/stream
```

API 层读取 `SseSink.get_queue_for(conversation_id)`，yield 每个事件：

```python
async def generator():
    queue = SseSink.get_queue_for(conversation_id)
    if queue:
        async for event in queue:
            yield event.as_sse()
```

---

## EventSink 接口

```python
class EventSink(ABC):
    async def emit(self, event: Event) -> None: ...
    async def emit_batch(self, events: List[Event]) -> None: ...
```

运行时 `Event` 类型：

| type | 含义 |
|------|------|
| `control.*` | 控制事件（调度决策、看门狗等） |
| `agent.*` | Agent 观测事件（thinking、token、tool_call 等） |
| `user.*` | 用户相关事件 |
| `system.*` | 系统级事件（session/round 生命周期） |

---

## AppEventBus（业务层）

业务层事件（消息、任务等）通过 `app_event_bus.publish(channel, event, data)` 发布：

```python
from app.events import app_event_bus

await app_event_bus.publish(
    f"conversation:{id}",
    "message:new",
    {"id": "...", "content": {...}}
)
```

订阅示例：

```python
async for event in app_event_bus.subscribe(channel):
    yield event.as_sse()
```

---

## 事件类型

### 运行时事件（EventDispatcher 分发）

| type | 含义 |
|------|------|
| `control.*` | 调度决策、看门狗等控制事件 |
| `agent.*` | Agent 观测事件（thinking、token、tool_call 等） |
| `user.*` | 用户相关事件 |
| `system.*` | session/round 生命周期事件 |

### 业务层事件（AppEventBus.publish）

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