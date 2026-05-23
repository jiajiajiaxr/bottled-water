# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AgentHub (codename `fish`) is a multi-agent collaboration IM workbench. It combines chat sessions, group conversations, an Agent marketplace, model management, tools, Skills, MCP, file context, artifact generation, a workflow canvas, and audit/permissions into a single platform.

**Frontend**: React 18 + TypeScript + Vite + Ant Design, served on port 5173.
**Backend**: Python 3.11 + FastAPI + SQLAlchemy + Alembic, served on port 8000.

## Common Commands

### Backend (uses `uv`)

```powershell
# Install dependencies
uv sync --project backend --extra dev

# Run migrations
uv run --project backend --directory backend alembic upgrade head

# Start dev server
uv run --project backend --directory backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Run all backend tests
uv run --project backend pytest -q

# Run a single test file
uv run --project backend pytest tests/test_conversation.py -q

# Run with live API base URL (acceptance mode)
uv run --project backend pytest tests --live-base-url http://localhost:8000
```

### Frontend (uses `corepack pnpm`)

```powershell
cd frontend
corepack pnpm install

# Start dev server (proxies /api/v1 to localhost:8000)
corepack pnpm dev

# Type check
corepack pnpm exec tsc --noEmit --pretty false

# Build
corepack pnpm build

# Run unit tests
corepack pnpm vitest run
```

### E2E Tests

```powershell
cd frontend
corepack pnpm exec playwright test -c ../e2e/playwright.config.ts
```

### Full Acceptance Suite

```powershell
.\scripts\run-acceptance.ps1
```

## Architecture

### Request Flow

```
User -> React IM Workbench (frontend/src/App.tsx)
  -> FastAPI API Layer (backend/app/api/)
  -> Orchestration Runtime (backend/app/services/orchestrator.py)
     - Single Chat: selected Agent loop
     - Group Chat: workflow canvas first
  -> Agentic Tool Loop (backend/app/services/agentic_runtime.py)
     - Model Gateway -> Tool Registry / Skill Runtime / MCP Runtime / File Tools / Artifact Tools
  -> Persistence (SQLAlchemy + SQLite locally, PostgreSQL/Redis compatible)
```

### Single Chat vs Group Chat

**Single chat** launches the selected Agent's short Agentic Loop directly:
```
User message -> selected Agent -> Agent model_config_id -> Agent tools/skills/mcp permissions
  -> run_agentic_tool_loop(...) -> streaming answer -> optional artifacts
```

**Group chat** uses the workflow canvas in `conversation.extra.workflow` as the source of truth:
```
User message -> load conversation.extra.workflow -> optional replan by authorized Agent
  -> execute workflow nodes by edges/order -> agent nodes call corresponding Agent loop
  -> condition/loop/tool/skill/mcp nodes persist runtime state
  -> reviewer/artifact/end nodes produce final response and artifacts
```

Master Agent is a regular Agent that defaults to planning/summarization. It no longer has implicit highest scheduling authority.

### Workflow Canvas

Workflow data lives in `conversation.extra.workflow` (nodes + edges). Runtime state is stored in `workflow_runs.node_states` and synced to `conversation.extra.workflow_runtime`.

Supported node types: `start`, `agent`, `tool`, `skill`, `mcp`, `condition`, `loop`, `review`, `artifact`, `end`.

### Output Filtering

Internal planning, task decomposition, execution steps, and review drafts should not appear in final chat bubbles.

- Backend filter: `backend/app/services/output_filter.py`
- Frontend filter: `frontend/src/App.tsx` function `stripInternalAgentOutput`
- Orchestration generation: `backend/app/services/orchestrator.py`

## Cross-Stack Changes

When adding a field that spans frontend and backend, the typical chain is:

1. `backend/app/models.py` — add SQLAlchemy model field
2. `backend/alembic/versions/` — add migration (`uv run --project backend --directory backend alembic revision --autogenerate -m "..."`)
3. `backend/app/services/serialization.py` — add output serialization
4. `frontend/src/types.ts` — add TypeScript type
5. `frontend/src/api.ts` — add API SDK method
6. `backend/app/api/*.py` — add/modify endpoint if needed
7. Tests in `tests/` and/or `frontend/tests/`

## Key Files

- `backend/app/main.py` — FastAPI entry, router registration
- `backend/app/core/config.py` — Settings from `.env` (reads project root `.env` then `backend/.env`)
- `backend/app/models.py` — All SQLAlchemy models
- `backend/app/services/orchestrator.py` — Core orchestration (single chat + group chat workflow execution)
- `backend/app/services/agentic_runtime.py` — Agent tool loop (tool/skill/MCP selection and execution)
- `backend/app/services/tool_registry.py` — Built-in tools, official Agent toolboxes, custom tool invocation
- `backend/app/services/ark.py` — Volcano Ark / OpenAI-compatible model adapter
- `backend/app/services/llm_gateway.py` — Model config and connectivity test
- `backend/app/services/file_tools.py` — File parsing, preview, conversion, summarization
- `backend/app/services/artifacts.py` — Artifact creation and preview cards
- `backend/app/services/mcp_runtime.py` — MCP tool invocation and call records
- `backend/app/services/output_filter.py` — Filter internal output from user-facing chat
- `frontend/src/App.tsx` — Main workbench (login, chat, Agent directory, workflow canvas, settings, preview)
- `frontend/src/api.ts` — Frontend API SDK
- `frontend/src/types.ts` — Frontend domain types

## Environment Configuration

Create a `.env` in the project root:

```env
DATABASE_URL=sqlite:///./agenthub_dev.db
LLM_PROVIDER=ark
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_ENDPOINT_ID=...
ARK_MODEL=...
ARK_API_KEY=...
```

- `LLM_PROVIDER=ark` — real Volcano Ark adapter
- `LLM_PROVIDER=mock` — local mock responses
- `LLM_PROVIDER=auto` — uses real model if key exists, else mock

API keys are backend-only. The frontend never handles real keys.

## Testing Notes

- Backend tests use `fastapi.testclient.TestClient` by default. Set `AGENTHUB_API_BASE_URL` or pass `--live-base-url` to test against a running server.
- The `auth_headers` fixture in `tests/conftest.py` auto-creates a test user via signup/login.
- Frontend unit tests use Vitest + jsdom with `frontend/tests/setup.ts` mocking `matchMedia`.
- E2E tests use Playwright with base URL defaulting to `http://localhost:5173`.
