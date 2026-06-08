# Event Protocol

AgentHub uses REST for ordinary state, SSE for streaming assistant responses, and WebSocket for compatible realtime chat paths.

## SSE Endpoint

```text
GET /api/v1/conversations/{conversation_id}/stream
```

The frontend also sends messages through REST endpoints that return/trigger stream events. See `frontend/src/api/message.ts` for merge behavior.

## Common Events

| Event | Purpose |
| --- | --- |
| `message_start` | Create or identify a streaming assistant message. |
| `content_block_delta` | Append text or reasoning delta. |
| `tool_call_start` | Show a tool call in progress. |
| `tool_call_done` | Merge tool result and mark call complete. |
| `message:new` | Insert a newly persisted message, such as an artifact card. |
| `message:updated` | Replace or merge a persisted message update. |
| `generation:failed` | Mark generation failed and clear running state. |
| `generation:cancelled` | Mark generation cancelled and clear running state. |
| `message_stop` | Mark normal streaming completion. |

Events should include stable IDs when possible:

- `conversation_id`
- `message_id` or `agent_message_id`
- `client_message_id`
- `agent_id`
- `agent_name`
- `tool_call_id`

Stable IDs prevent duplicate bubbles when reconnecting or merging final persisted messages.

## Frontend Merge Rules

Frontend stream handling should:

- Create a placeholder message on `message_start`.
- Append deltas to the same message ID.
- Merge final persisted messages without duplicating the streaming placeholder.
- Clear local running-conversation state on success, failure, or cancellation.
- Keep tool call summaries separate from final user-visible answer text.

Relevant code:

- `frontend/src/api/message.ts`
- `frontend/src/lib/message.ts`
- `frontend/src/lib/runningConversations.ts`
- `frontend/src/store/useMessageStore.ts`

## WebSocket

Conversation WebSocket endpoint:

```text
/ws/conversations/{conversation_id}?token=...
```

Global compatibility endpoint:

```text
/ws
```

The Docker nginx config proxies both `/ws/` and `/ws` to the backend.

## Backend Event Sources

- Message streaming: `backend/src/app/api/messages.py`
- WebSocket chat: `backend/src/app/api/websocket.py`
- Realtime services: `backend/src/app/services/realtime`
- Chat finalization/cancellation: `backend/src/app/services/chat`
- Runtime events: `backend/src/agent_runtime`

## Protocol Contract

- Do not fabricate terminal success. If a model, tool, MCP server, sandbox, or external agent fails, emit a failure event and persist the error where appropriate.
- Tool and artifact cards should come from persisted tool/artifact results.
- Long-running streams must have a terminal event so the frontend can clear running state.
