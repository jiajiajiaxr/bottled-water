# Current Implementation Status

This file is the compact status reference for current docs. It avoids historical closure notes and only tracks present behavior and known boundaries.

## Stable For Local Development And Demos

- Authentication, demo login, users, workspaces, projects, and conversation management.
- Single-agent and group conversations with persisted messages and streaming responses.
- Agent directory and configurable model/tool/skill/MCP permissions.
- Tool catalog, built-in tools, invocation records, and permission checks.
- External coding agent tools for Codex and Claude Code, including persisted runs and status/cancel paths.
- Model provider management and Ark/OpenAI-compatible fallback configuration.
- File upload, workspace file tree, preview/download operations, and attachment context.
- Artifact generation, preview, versioning, diff, export, and deployment preview records.
- Workflow generation, editing, save/enable, run start, polling, runtime state persistence, and real node execution for supported node types.
- Skill and MCP management with probe, invoke, and recorded degraded failures when external runtimes are unavailable.
- Security operations for audit logs, roles, permissions, and user role changes.
- Docker compose deployment for nginx, backend, PostgreSQL, and Redis.

## Implemented With Environment-Dependent Degradation

- Real LLM responses depend on configured model provider credentials. Without keys, local mock/fallback behavior is expected.
- Office/PDF preview quality depends on available conversion tools in the runtime environment.
- Sandbox and external coding agent execution depend on installed command runtimes and workspace-safe cwd constraints.
- MCP stdio/HTTP calls depend on external server availability and declared transport support.
- Deployment preview validates accessible artifacts; full production cloud/container deployment remains outside the current local runtime.

## Recently Hardened

- Workflow run state no longer relies on static 5% progress and merges persisted node/run state during polling.
- Workflow save accepts canvas object edges and updates conversation runtime mode when enabled.
- AI workflow generation uses backend generation logic instead of static examples.
- Ark streaming tool-call parsing now handles `finish_reason == "tool_calls"` correctly.
- Daily Chat context summaries now reflect default full tool permissions, including Claude Code tools.
- Docker one-command deployment now uses correct build contexts, backend `PYTHONPATH`, startup migrations, psycopg Postgres URLs, nginx streaming/WebSocket proxying, and Docker-specific env isolation.

## Roadmap / Not A Current Guarantee

- Distributed multi-process runtime coordination without sticky sessions.
- Production-grade remote control and cloud deployment automation.
- Enterprise approval workflows and advanced audit search.
- Fully isolated production container sandbox policy. The current local sandbox has command/cwd/time/output controls, but production isolation belongs to deployment infrastructure.
- Broad document rendering parity across every Office feature without environment-specific conversion dependencies.

## Maintenance Rule

When a feature changes, update the closest source-of-truth document:

- Product flow: `docs/functional-guide.md`
- Code ownership: `docs/file-map.md`
- Backend/runtime design: `docs/backend-architecture.md` or `docs/agent-workflow-runtime.md`
- Events: `docs/event-protocol.md`
- Deployment: `docker/README.md` and `docs/development-guide.md`
