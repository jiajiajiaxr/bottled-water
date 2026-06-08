# AgentHub Documentation

This directory contains the current documentation for AgentHub. Historical design notes and dated implementation plans have been removed so the docs describe the system as it exists now.

## Start Here

- [Development guide](./development-guide.md): local setup, Docker deployment, tests, and common workflows.
- [Feature guide](./functional-guide.md): product capabilities and user-facing flows.
- [File map](./file-map.md): where the important backend, frontend, test, and deployment files live.
- [Backend architecture](./backend-architecture.md): FastAPI, persistence, runtime services, tools, skills, MCP, and workflow execution.
- [Workflow runtime](./agent-workflow-runtime.md): single chat, group chat, workflow canvas, node execution, and persisted run state.
- [Event protocol](./event-protocol.md): SSE/WebSocket event names and frontend merge behavior.
- [Capability and data boundaries](./capability-data-boundaries.md): permissions, data ownership, and runtime safety boundaries.
- [Current status](./implementation-status.md): what is complete, what is hardened enough for demos, and what remains a roadmap item.

## Source Of Truth

- Backend source of truth: `backend/src`.
- Frontend source of truth: `frontend/src`.
- Database schema source of truth: `backend/src/db/models` plus `backend/alembic/versions`.
- Deployment source of truth: `docker/docker-compose.yml`, `docker/Dockerfile.backend`, `docker/Dockerfile.frontend`, and `docker/nginx.conf`.

`backend/app-old` is historical reference only. Do not use it for new implementation or documentation examples.

## Current Architecture At A Glance

```text
React Workbench
  -> API client / SSE / WebSocket
  -> FastAPI routers
  -> chat, workflow, agent, tool, skill, MCP, file, artifact services
  -> SQLAlchemy models and Alembic migrations
  -> model providers, sandbox, external coding agents, deployment preview
```

Single-agent chats run the selected agent's loop. Group chats use the conversation scheduling settings. When `workflow_enabled=true`, the saved workflow canvas is the execution plan; otherwise the runtime can use the tech-lead/actor orchestration path.

## Documentation Rules

- Keep docs tied to current code paths.
- Put long-lived architecture and operating guidance here.
- Avoid adding dated closure notes, brainstorming plans, or migration journals.
- If a roadmap item is not implemented, label it as roadmap instead of describing it as available behavior.
