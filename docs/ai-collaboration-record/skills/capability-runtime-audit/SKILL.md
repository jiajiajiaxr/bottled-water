---
name: capability-runtime-audit
description: Use this skill when checking whether AgentHub Tool, Skill, MCP, sandbox, file, artifact, deployment, or external coding agent capabilities are real, authorized, recorded, and recoverable.
---

# Capability Runtime Audit

## Purpose

Use this skill when auditing AgentHub's capability system. It ensures that tools are not merely exposed in UI, but are correctly authorized, executed, recorded, surfaced to chat, and recoverable after refresh.

## Audit Chain

For every capability, trace:

1. Catalog visibility.
2. Agent authorization.
3. Function-call schema exposure.
4. Runtime invocation.
5. Permission and JSON schema validation.
6. Execution result.
7. Run record persistence.
8. Chat or workflow surface.
9. Workspace file or artifact side effect.
10. Error behavior.

## Capability Types

- Built-in tools.
- Custom Python tools.
- Skill runtime.
- MCP servers and tools.
- Sandbox commands.
- File upload/read/write/preview.
- Artifact generation/export/deploy.
- External Coding Agent runs.

## Prompt Pattern

```text
请审计这个能力链路是否真实可用：
从目录、授权、Function Call 暴露、执行、记录、聊天展示、刷新恢复和错误回传逐层检查。
不允许只看前端是否显示按钮。
```

## Acceptance

The audit passes only when a successful call has a durable record and a failed call has a clear user-facing reason without blocking the conversation.
