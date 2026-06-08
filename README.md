# AgentHub

AgentHub is a multi-agent IM workbench. It combines chat, group collaboration, agent configuration, model providers, tools, skills, MCP servers, workspace files, artifacts, workflow orchestration, audit logs, and preview deployment in one product surface.

The current implementation is centered on:

- `backend/src`: FastAPI, SQLAlchemy, Alembic, runtime services, tools, skills, MCP, files, artifacts, and workflow execution.
- `frontend/src`: React 18, TypeScript, Vite, Ant Design, Zustand, chat workbench, platform panels, preview panel, workflow studio, and docs page.
- `docker/`: one-command local deployment with nginx, backend, PostgreSQL, and Redis.

`backend/app-old` is retained only as historical reference. New work should go into `backend/src`.

## What Works Today

- User auth, demo login, workspaces, projects, conversation lists, archive/pin/category flows.
- Single-agent chat and multi-agent group chat with SSE/WebSocket streaming.
- Model provider configuration, including Ark/OpenAI-compatible model access and mock fallback.
- Agent directory with configurable model, tool, skill, MCP, and loop strategy permissions.
- Built-in tools for files, artifacts, sandbox execution, browser preview, deployment preview, database inspection, security audit, tests, and external coding agents.
- Real external coding agent tool entries for Codex and Claude Code, including probe, run, status, cancel, persisted run records, and tool invocation logs.
- Skills and MCP server management with probe, invocation, and persisted invocation records.
- Workspace files, uploaded attachments, text extraction, preview, Office-to-PDF fallback paths, and knowledge entry points.
- Artifact generation and lifecycle for HTML/Web apps and office/document formats, with preview, edit, diff, export, and deployment preview records.
- Workflow canvas generation, editing, saving, enabling, running, node state persistence, and real tool/agent node execution.
- Security operations panel with audit logs, roles, permissions, and user role updates.
- Docker deployment stack for local or demo environments.

## Quick Start

Backend:

```powershell
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Frontend:

```powershell
cd frontend
pnpm install
pnpm dev
```

Open the frontend at `http://localhost:5173`.

## Docker Deployment

From the repository root:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

Open `http://localhost`.

To customize passwords, public URL, or exposed port:

```powershell
Copy-Item docker/env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up --build
```

See [docker/README.md](./docker/README.md).

## Configuration

The backend reads environment values from the repository `.env`, then `backend/.env`, then process environment.

Common local values:

```env
DATABASE_URL=sqlite:///./agenthub_dev.db
SECRET_KEY=change-me
LLM_PROVIDER=auto
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_API_KEY=
ARK_ENDPOINT_ID=
ENABLE_FUNCTION_CALLING=true
```

For Docker, prefer `docker/.env` based on [docker/env.example](./docker/env.example). The compose file builds the PostgreSQL `DATABASE_URL` from `POSTGRES_*` values so the root development `.env` does not accidentally force SQLite inside containers.

## Tests

Backend:

```powershell
cd backend
uv run ruff check .
uv run pytest -q
```

Frontend:

```powershell
cd frontend
pnpm build
pnpm exec vitest run --config tests/vitest.config.ts
```

## Documentation

- [Docs index](./docs/README.md)
- [Development guide](./docs/development-guide.md)
- [Feature guide](./docs/functional-guide.md)
- [Backend architecture](./docs/backend-architecture.md)
- [Workflow runtime](./docs/agent-workflow-runtime.md)
- [Event protocol](./docs/event-protocol.md)
- [File map](./docs/file-map.md)
- [Capability and data boundaries](./docs/capability-data-boundaries.md)
- [Current implementation status](./docs/implementation-status.md)
