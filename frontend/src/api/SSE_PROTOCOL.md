# AgentHub SSE 流式协议文档

> 基于前端 `api/client.ts` 与 `api/message.ts` 反推的后端 SSE 协议规范。

---

## 1. 连接建立

**Endpoint:**

```
GET /api/v1/conversations/{conversationId}/stream?replay=false&token={token}
```

**参数:**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `conversationId` | string | 是 | 对话 ID |
| `replay` | boolean | 否 | 是否重播历史流式内容，默认 `false` |
| `token` | string | 否 | 认证 token |

**返回:** `text/event-stream`

---

## 2. 事件类型总览

后端通过 SSE 向下述事件名推送数据，前端按对应 handler 处理：

| SSE 事件名 | 前端 Handler | 触发时机 |
|-----------|-------------|---------|
| `message_start` | `onMessageStart` | 模型开始生成回复 |
| `content_block_delta` | `onDelta` / `onReasoningDelta` | 收到内容增量片段 |
| `message:updated` | `onMessageUpdated` | 流式结束后推送完整消息 |
| `message:new` | `onMessageNew` | 推送新消息（如产物卡片） |
| `tool_call_start` | `onToolCallStart` | Agent 开始调用工具 |
| `tool_call_done` | `onToolCallDone` | Agent 工具调用结束 |
| `message_stop` | `onDone` | SSE 正常结束 |
| `error` (EventSource error) | `onDone` | 连接异常 |

---

## 3. 各事件详细格式

### 3.1 message_start

标志模型开始生成回复。前端收到后创建流式占位消息。

**Payload 结构:**

```json
{
  "agent_message_id": "msg-xxx",
  "message_id": "msg-yyy",
  "agent_id": "agent-123",
  "agent_name": "CodeAgent",
  "sender_name": "CodeAgent"
}
```

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_message_id` | string | 推荐 | 本次 Agent 回复的消息 ID |
| `message_id` | string | 备选 | 消息 ID（若 `agent_message_id` 为空则用它） |
| `agent_id` | string | 推荐 | Agent 唯一标识 |
| `agent_name` | string | 推荐 | Agent 显示名称 |
| `sender_name` | string | 备选 | 发送者名称（若 `agent_name` 为空则用它） |

**注意:**

- `agent_id` 强烈建议推送，否则前端只能通过 `agent_name` 匹配占位消息，容易失配导致重复气泡。

---

### 3.2 content_block_delta

推送内容增量。同一个回复会连续推送多个 delta，前端需要累积。

**Payload 结构:**

```json
{
  "agent_message_id": "msg-xxx",
  "message_id": "msg-yyy",
  "agent_id": "agent-123",
  "agent_name": "CodeAgent",
  "delta": {
    "type": "text_delta",
    "text": "这段"
  }
}
```

**delta.type 枚举:**

| 类型 | 前端处理 | 说明 |
|------|---------|------|
| `text_delta` | `onDelta` | 正文内容增量 |
| `reasoning_delta` | `onReasoningDelta` | thinking 内容增量 |

**字段说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_message_id` | string | 推荐 | 所属消息 ID |
| `message_id` | string | 备选 | 同上 |
| `agent_id` | string | 推荐 | Agent ID |
| `agent_name` | string | 推荐 | Agent 名称 |
| `delta.type` | string | 是 | `text_delta` 或 `reasoning_delta` |
| `delta.text` | string | 是 | 增量文本片段 |

**注意:**

- 同一个回复的所有 delta 应该使用相同的 `agent_message_id`，否则前端会认为是不同消息，创建多个气泡。
- `delta.text` 可能为空字符串，前端会忽略。

---
