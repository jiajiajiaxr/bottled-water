---
name: multi-agent-runtime-debug
description: Use this skill when debugging AgentHub multi-agent chat, scheduler decisions, actor runtime, workflow execution, streaming messages, or conversation running-state problems. It focuses on event semantics, per-conversation isolation, and agent identity preservation.
---

# Multi-agent Runtime Debug

## Purpose

Use this skill when AgentHub group chat, automatic organization, workflow execution, or streaming output behaves incorrectly. The goal is to preserve the intended runtime model: each conversation owns its session, each agent owns its messages, and global running state ends only on generation completion, cancellation, or failure.

## Runtime Model

- Single chat: `single_agent`.
- Default group chat: `tech_lead` actor runtime.
- Workflow mode: enabled explicitly by conversation workflow settings.
- `message_stop` ends one assistant message.
- `generation_finished`, `cancelled`, or failed terminal events end the global running state.
- `@Agent` should target the mentioned agent unless the user asks for broader collaboration.

## Debug Checklist

1. Confirm the conversation mode: single, automatic organization, or workflow.
2. Confirm the active generation id belongs to the current conversation.
3. Check whether assistant messages are created once and updated by id.
4. Check whether stream deltas append to the correct `agent_message_id`.
5. Ensure switching conversations does not detach or drop the active stream.
6. Verify terminal events clear only the matching conversation's running state.
7. For group chat, verify scheduler decisions use agent names, roles, dependencies, and current members.

## Common Failure Patterns

- A placeholder message and a real message both render, then one disappears.
- A message streams but final DB refresh replaces it with a duplicate.
- One agent's output overwrites another agent's output.
- Group chat answers only once after the first turn.
- The UI shows "thinking" forever even though the backend completed.
- Workflow mode silently runs when workflow is saved but not enabled.

## Good Prompt Shape

```text
请不要用补拉消息掩盖流式问题。
从 WebSocket/SSE 事件、message id、generation id、conversation id 和前端 reducer 逐层检查。
确保单聊、自动组织群聊、工作流模式都使用同一套事件语义。
```

## Acceptance

The fix is acceptable when:

- A user can switch conversations during streaming and return without losing the live message.
- Multiple agents can stream without overwriting each other.
- A completed generation clears running state.
- Refreshing the page restores completed messages and does not resurrect stale running state.
