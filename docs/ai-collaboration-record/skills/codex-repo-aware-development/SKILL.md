---
name: codex-repo-aware-development
description: Use this skill when developing AgentHub with Codex. It guides Codex to read the repository, docs, branch state, architecture boundaries, and recent history before modifying code, so changes stay aligned with the current project structure instead of becoming isolated patches.
---

# Codex Repo-aware Development

## Purpose

Use this skill when a task requires modifying AgentHub code, documentation, tests, or product behavior. The goal is to make Codex act like a repository-aware engineering partner: understand the current system first, then implement within the established architecture.

## Required Context Pass

Before editing, inspect only the context needed for the task:

1. Read `CLAUDE.md` for local development rules.
2. Read relevant docs under `docs/`, especially architecture, runtime, tool, workflow, or file-system docs when the task touches those areas.
3. Check `git status --short` and avoid overwriting unrelated user changes.
4. Search with `rg` for real implementation entry points before assuming where logic lives.
5. Prefer current paths such as `backend/src` and `frontend/src`; treat old compatibility entries as shims unless the task explicitly targets them.

## Architecture Guardrails

- Keep business logic in the correct domain module.
- Do not put new behavior into deprecated orchestrator, tool registry, or legacy direct-agent paths.
- Preserve existing APIs unless the task explicitly changes them.
- Use small focused edits and keep unrelated refactors out of the patch.
- If a behavior crosses backend, frontend, and docs, update all affected surfaces.

## Workflow

1. Identify the active user-facing bug or feature.
2. Map it to backend service, frontend state, database model, realtime event, and documentation surfaces.
3. Make the smallest complete implementation that closes the loop.
4. Verify with targeted commands or browser checks when needed.
5. Summarize the changed files, reason, and remaining risk.

## Good Prompt Shape

```text
请先阅读 CLAUDE.md 和相关 docs，确认当前主链路。
只改当前功能涉及的模块，不要改旧入口。
如果涉及工具/产物/消息流，请同时检查后端事件、数据库记录、前端状态和刷新恢复。
```

## Acceptance

A change is complete only when:

- It follows the current module boundary.
- It does not rely on fake UI-only state.
- It survives refresh or conversation switching when the feature requires persistence.
- It has a clear explanation in code or docs if the behavior is non-obvious.
