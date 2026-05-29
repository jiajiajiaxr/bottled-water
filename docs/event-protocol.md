# AgentHub 事件协议文档

## 概述

AgentHub 后端使用双层事件机制：

| 层级 | 实现 | 用途 |
|------|------|------|
| **运行时事件** | `SSEEventSink`（agent_runtime） | 多 Agent 调度中的内部事件（决策、报告等） |
| **应用事件** | `EventBus`（app.services） | 业务层事件（消息、任务、SSE 推送等） |

两者通过不同路径产生，最终都通过 SSE 流推送给前端。

---

## SSE 端点

```
POST /api/v1/conversations/{conversation_id}/stream
```

返回 `text/event-stream`，订阅 `conversation:{id}` 频道。

---

## 应用层事件（EventBus）

事件通过 `EventBus` 推送，频道为 `conversation:{id}`。

### Event 数据结构

```python
@dataclass
class Event:
    event: str          # 事件名称
    data: dict          # 事件数据
    timestamp: str      # ISO 时间戳
```

### as_sse() 格式

```python
{"event": "message:new", "data": '{"id": "...", "content": {...}}'}
```

---

## 事件类型一览

### 消息事件

| 事件名 | 含义 | 典型 data |
|--------|------|-----------|
| `message:new` | 新消息创建 | Message 对象字典 |
| `message:updated` | 消息内容更新 | `{"id": "...", "updated_fields": [...]}` |
| `message_start` | Agent 消息流开始 | `{"agent_message_id": "...", "agent_id": "..."}` |
| `content_block_delta` | 流式文本片段 | `{"agent_message_id": "...", "delta": {"type": "text_delta", "text": "..."}}` |
| `message_stop` | Agent 消息流结束 | `{"agent_message_id": "...", "stop_reason": "end_turn"}` |

### 编排事件

| 事件名 | 含义 | 典型 data |
|--------|------|-----------|
| `orchestrator:error` | 编排器异常 | `{"error": "...", "error_type": "RuntimeError"}` |
| `generation:cancelled` | 生成被用户取消 | `{"conversation_id": "...", "cancelled": true}` |

### 任务事件

| 事件名 | 含义 | 典型 data |
|--------|------|-----------|
| `task:status_changed` | 任务状态变更 | Task 字典 |
| `task:subtask_updated` | 子任务状态变更 | Subtask 字典 |

### 工作流事件

| 事件名 | 含义 | 典型 data |
|--------|------|-----------|
| `workflow:run_updated` | Workflow 运行状态更新 | `{"run_id": "...", "status": "running", "progress": 30, "node_id": "..."}` |

### 工具事件

| 事件名 | 含义 | 典型 data |
|--------|------|-----------|
| `tool:started` | 工具开始执行 | `{"agent_id": "...", "tool_name": "...", "status": "running"}` |
| `tool:finished` | 工具执行完成 | `{"agent_name": "...", "tool_name": "...", "status": "success", "output": {...}}` |

---

## 运行时事件（SSEEventSink）

`agent_runtime` 产生的原生事件，经 `EventSink` 接口注入。

### Event 类型（agent_runtime/core/types.py）

| type | 含义 |
|------|------|
| `round_start` | 调度轮次开始 |
| `round_end` | 调度轮次结束 |
| `decision` | 调度决策 |
| `assign` | Agent 指派 |
| `agent_report` | Agent 状态报告 |
| `tool_call` | 工具调用 |
| `tool_result` | 工具返回结果 |
| `message` | 运行时消息 |
| `complete` | 执行完成 |
| `error` | 运行时错误 |

### 使用方式

```python
from app.events.sse_sink import SSEEventSink

session = AgentSession.create(
    event_sink=SSEEventSink(conversation_id=str(conversation.id)),
    ...
)
```

### 获取队列

```python
queue = SSEEventSink.get_queue_for(conversation_id)
```

---

## 已知问题

### 1. 双事件系统并存

`EventBus` 和 `SSEEventSink` 是两套独立的机制：

- `EventBus` 是实际被 SSE 端点消费的（通过 `event_bus.subscribe`）
- `SSEEventSink` 定义的 Queue 没有被 SSE 端点读取

**建议**：统一由 `EventBus` 作为唯一出口，`SSEEventSink` 改为向 `EventBus` 发布事件。

### 2. SSEEventSink 与 EventBus 重复

目前 `SSEEventSink` 的 Queue 和 `EventBus` 的队列并存，两边都推同一会话的事件但路径不同。

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
  // 处理新消息
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

## Redis 集成

`EventBus` 使用 Redis 作为可选的跨进程消息总线：

- `publish(channel, payload)` → Redis pub/sub
- `xadd(stream:{channel}, ...)` → Redis stream 历史

本地开发无 Redis 时自动降级，仅走内存队列。