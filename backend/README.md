# AgentHub Backend

FastAPI backend for AgentHub.

## Stack

- Python 3.11
- FastAPI
- SQLAlchemy 2 async ORM
- Alembic
- Pydantic
- uv
- SQLite for local development, PostgreSQL for Docker/demo deployment

## Layout

```text
backend/
  alembic/             database migrations
  src/
    app/
      api/             FastAPI routers
      core/            config, security, errors, responses, logging
      events/          realtime event sinks
      persistence/     runtime persistence adapter
      schemas/         Pydantic schemas
      services/        business services
    agent_runtime/     orchestration/runtime primitives
    common/            shared helpers
    db/                database config, session, models
    model_provider/    model provider abstraction
  tests/               pytest suite
```

## Local Run

```powershell
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Tests

```powershell
uv run ruff check .
uv run pytest -q
```

Targeted checks:

```powershell
uv run pytest tests/test_conversation.py tests/test_context_system.py tests/test_external_agents.py -q
```

## Key Domains

- `api/conversations.py`: conversations, participants, workflow canvas, workflow runs.
- `api/messages.py`: message send/list/stream/cancel.
- `api/agents.py`: agent directory and agent configuration.
- `api/tools.py`: tool catalog and invocation.
- `api/skills.py`: skill creation, generation, testing, and MCP import.
- `api/mcp.py`: MCP server management and invocation.
- `api/external_agents.py`: Codex and Claude Code run records.
- `api/files.py` and `api/workspace_files.py`: file upload, workspace file tree, preview, and download.
- `api/artifacts.py`: artifact lifecycle.
- `api/deployments.py`: deployment preview records.
- `api/security_ops.py`: audit, roles, permissions.

## Notes

- `backend/app-old` is historical reference only.
- Database URLs using `postgresql://` are normalized to `postgresql+psycopg://`.
- When changing nested JSON columns such as `Conversation.extra` or `WorkflowRun.node_states`, use existing runtime helpers or flag changes explicitly.
