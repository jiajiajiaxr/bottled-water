---
name: computer-use-self-review
description: Use this skill when AgentHub changes need real user-experience validation. It defines how Codex uses Browser or Computer Use style checks to inspect local pages, click UI controls, verify screenshots, and turn visual or interaction failures into concrete engineering fixes.
---

# Computer Use Self-review

## Purpose

Use this skill after UI, workflow, preview, deployment, file, or chat-streaming changes. The goal is to avoid stopping at "the API returned 200" and instead verify what a real user sees and clicks.

## Review Surfaces

Check the smallest surface that proves the feature:

- Chat: send messages, switch conversations, observe streaming and final state.
- Artifact preview: click preview cards, open right panel, download the real file.
- Workflow canvas: drag nodes, edit config, connect edges, run and inspect state.
- Workspace files: upload, preview, rename, delete, refresh, and verify tree/map state.
- Settings and agent drawers: edit permissions, save, reload, and confirm persistence.

## Self-review Loop

1. Open the local page or use the current in-app browser.
2. Perform the exact user action described in the bug or requirement.
3. Observe visual state, loading state, console/API behavior, and persistence after refresh.
4. If the UI has no response, trace from click handler to API call to backend result.
5. If the backend succeeds but UI fails, inspect state mapping and event handling.
6. Patch the smallest responsible layer.
7. Re-open or refresh and repeat the action once.

## What To Look For

- White screen, blank panel, or silent click.
- Duplicated assistant messages or duplicated preview cards.
- "running" or "thinking" labels that survive completion.
- Preview or deployment status that says success without a usable URL.
- Text overflow, misaligned cards, hidden buttons, or unusable inputs.
- Old global state affecting a different conversation.

## Good Prompt Shape

```text
请像真实用户一样打开页面验证：
点击按钮、切换会话、刷新页面、再回到原会话。
不要只看接口 200，要确认页面上确实显示正确结果。
如果发现问题，请从 UI 事件、API 响应、DB 状态和实时事件逐层定位。
```

## Evidence To Record

- The route or screen checked.
- The action performed.
- The visible failure or success.
- The file/module responsible for the fix.
- Whether refresh or conversation switching still works.
