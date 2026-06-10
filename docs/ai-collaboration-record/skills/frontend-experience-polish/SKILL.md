---
name: frontend-experience-polish
description: Use this skill when AgentHub frontend work requires mature product polish: layout stability, streaming feedback, preview panels, workflow canvas interaction, file tree usability, or mobile-safe visual hierarchy.
---

# Frontend Experience Polish

## Purpose

Use this skill for UI and interaction refinement where "works technically" is not enough. AgentHub is an IM-style AI workbench, so the frontend must feel stable, responsive, and understandable while agents are working.

## Focus Areas

- Message streaming should appear progressively, not suddenly after completion.
- Thinking blocks should respect the user's per-message thinking setting.
- Preview panels should open, close, resize, and recover after switching conversations.
- Workflow canvas should support drag, connect, edit, save, and visible runtime state.
- File trees should avoid UUID noise and preserve readable hierarchy.
- Long Chinese and English text must not overflow buttons, cards, or nodes.
- Loading states should be meaningful, not permanent spinners.

## Workflow

1. Reproduce the user action.
2. Observe the first 500 ms, the streaming phase, completion, switching away/back, and refresh.
3. Check both empty, loading, success, failed, and cancelled states.
4. Fix layout with stable dimensions and ellipsis rather than fragile text wrapping.
5. Keep product controls discoverable with concise labels and tooltips.

## Prompt Pattern

```text
请按成熟 SaaS 工作台标准优化这个交互：
不要只修接口成功，要检查加载态、空态、失败态、刷新恢复、文字溢出和切换会话后的状态。
```

## Acceptance

The feature is acceptable when a user can understand what is happening without reading logs, and no visible state contradicts the backend result.
