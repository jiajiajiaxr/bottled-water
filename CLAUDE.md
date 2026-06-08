# CLAUDE.md

This file gives Claude Code and other coding agents a compact orientation for this repository.

## Project

AgentHub is a multi-agent IM workbench with chat, group collaboration, agents, model providers, tools, skills, MCP servers, workspace files, artifacts, workflow orchestration, audit logs, external coding agents, and preview deployment.

Current source of truth:

- Backend: `backend/src`
- Frontend: `frontend/src`
- Docker deployment: `docker`
- Documentation: `README.md` and `docs`

`backend/app-old` is historical reference only.

## Read First

- `README.md`: project overview and quick start.
- `docs/development-guide.md`: local setup, Docker, tests, and common changes.
- `docs/file-map.md`: current file ownership map.
- `docs/backend-architecture.md`: backend structure and service boundaries.
- `docs/agent-workflow-runtime.md`: chat/workflow runtime.
- `docs/implementation-status.md`: current capability status and roadmap boundaries.

## Backend

Use Python 3.11 and `uv`.

```powershell
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run ruff check .
uv run pytest -q
```

Keep routers thin. Put business behavior in `backend/src/app/services`, schema changes in `backend/src/db/models` plus Alembic migrations, and tests in `backend/tests`.

## Frontend

Use TypeScript, React 18, Vite, Ant Design, Zustand, and pnpm.

```powershell
cd frontend
pnpm install
pnpm build
pnpm exec vitest run --config tests/vitest.config.ts
```

Main product surfaces live under `frontend/src/features`, `frontend/src/pages`, `frontend/src/api`, `frontend/src/store`, and `frontend/src/types`.

## Docker

From the repository root:

```powershell
docker compose -f docker/docker-compose.yml up --build
```

For custom values:

```powershell
Copy-Item docker/env.example docker/.env
docker compose --env-file docker/.env -f docker/docker-compose.yml up --build
```

## Safety Rules

- Do not put real model provider keys or secrets in frontend code.
- Do not treat tool, MCP, sandbox, deployment, or external coding agent actions as successful unless the backend persisted a successful result.
- Do not add new implementation under `backend/app-old`.
- When changing nested JSON state such as workflow runtime data, make sure SQLAlchemy persists the mutation.
