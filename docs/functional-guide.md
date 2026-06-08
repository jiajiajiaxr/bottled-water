# Feature Guide

AgentHub is organized around conversations. A user starts from an IM-style workbench, chooses a workspace and conversation, then collaborates with one or more agents. Files, tools, artifacts, workflows, and deployment records all attach back to the workspace or conversation.

## Authentication And Workspaces

- Users can register, log in, use demo login, update profile, and change password.
- Workspaces isolate conversations, files, projects, knowledge entries, and audit context.
- The workbench keeps workspace and conversation route state synchronized so direct links can reopen the same context.

Key code:

- Backend: `backend/src/app/api/auth.py`, `backend/src/app/api/workspaces.py`
- Frontend: `frontend/src/features/auth`, `frontend/src/features/workspaceFiles`, `frontend/src/pages/WorkbenchPage`

## Conversations

AgentHub supports:

- Single chat with a selected agent.
- Group chat with multiple agents.
- Conversation categories, pinning, archiving, unread state, members, and metadata.
- Streaming responses over SSE and WebSocket-compatible paths.
- Stop/cancel generation, retry, and persisted message history.

Single chat runs the selected agent loop. Group chat chooses scheduling from conversation settings. When workflow mode is enabled, the workflow canvas drives execution.

Key code:

- Backend: `backend/src/app/api/conversations.py`, `backend/src/app/api/messages.py`, `backend/src/app/api/websocket.py`
- Frontend: `frontend/src/features/chat`, `frontend/src/api/message.ts`, `frontend/src/api/websocket.ts`

## Agents

Agents can be official seeded agents or user-created agents. They can be configured with:

- Model config
- System prompt and description
- Tools
- Skills
- MCP tools
- Agentic loop settings

Agent tool access is permission-driven. If an agent has default full permissions, backend execution and context summaries now both expose the same effective tool set.

Key code:

- Backend: `backend/src/app/api/agents.py`, `backend/src/app/services/agents`, `backend/src/app/services/tools`
- Frontend: `frontend/src/features/agents`

## Models

The model layer supports provider and model configuration through the app. Ark/OpenAI-compatible fallback environment variables remain available for local bootstrap and tests.

Key code:

- Backend: `backend/src/app/api/models.py`, `backend/src/app/services/llm`
- Frontend: `frontend/src/features/settings`

## Tools

The tool catalog includes built-in and custom tools. Built-ins cover:

- File read/write/extract/preview/convert/summarize/embed/upload
- Artifact create/preview/revise/diff/export
- Sandbox command execution
- Browser preview
- API test and test runner
- Database inspection
- Deployment preview and rollback
- Security audit
- External coding agent probe/run/status/cancel

Tool calls are recorded through persisted invocation records. Agents must use real tool results as facts; UI cards and deployment states should not be faked by text-only answers.

Key code:

- Catalog and execution: `backend/src/app/services/tools`
- Built-ins: `backend/src/app/services/tools/builtins`
- API: `backend/src/app/api/tools.py`

## External Coding Agents

External agent support exposes Codex and Claude Code as real tool-call targets:

- `external_agent.probe`
- `external_agent.run_codex`
- `external_agent.run_claude_code`
- `external_agent.status`
- `external_agent.cancel`

Runs persist provider, command, cwd, stdout, stderr, changed files, status, exit code, duration, and error message. CWD is constrained to workspace-safe paths.

Key code:

- Backend: `backend/src/app/services/external_agents`, `backend/src/app/api/external_agents.py`
- Tests: `backend/tests/test_external_agents.py`

## Skills And MCP

Skills can be created, generated, tested, and imported from MCP definitions. MCP servers can be registered, probed, invoked, and audited. HTTP and stdio transports are handled through the MCP service layer; unavailable external runtimes degrade with explicit errors.

Key code:

- Skills: `backend/src/app/api/skills.py`, `backend/src/app/services/skills`
- MCP: `backend/src/app/api/mcp.py`, `backend/src/app/services/mcp`
- Frontend: `frontend/src/features/platform/tabs`

## Files And Knowledge

The file system supports upload, workspace file browsing, preview, download, rename, move, favorite, delete, and bulk delete. Uploaded files can be extracted and included in runtime context. Knowledge features provide lightweight knowledge-base import and retrieval paths.

Office preview can use PDF conversion where the runtime environment provides the required tools; otherwise the backend should return a clear degraded result.

Key code:

- Backend: `backend/src/app/api/files.py`, `backend/src/app/api/workspace_files.py`, `backend/src/app/services/files`
- Frontend: `frontend/src/features/workspaceFiles`

## Artifacts And Preview

Artifacts represent deliverable outputs. HTML/Web app, PDF, DOCX, PPTX, XLSX, and related formats can be created through the tool layer, opened in the preview panel, edited, diffed, exported, and used for deployment preview records.

Key code:

- Backend: `backend/src/app/api/artifacts.py`, `backend/src/app/services/artifacts.py`, `backend/src/app/services/document_model`
- Frontend: `frontend/src/features/preview`

## Workflows

Workflow canvases are saved under conversation metadata and can be generated, edited, enabled, and run. Supported node categories include start, agent, tool, skill, MCP, condition, loop, review, artifact, and end.

Recent behavior:

- AI workflow generation uses the backend generation path instead of static samples.
- Workflow saves normalize canvas-style edges and preserve runtime settings.
- Enabling a saved workflow updates the conversation scheduling mode.
- Run state is persisted and merged during polling so runs no longer appear stuck at an artificial 5%.

Key code:

- Backend: `backend/src/app/api/conversations.py`, `backend/src/app/services/workflows`
- Frontend: `frontend/src/features/workflow`, `frontend/src/features/platform/tabs/WorkflowBoardPanel`
- Tests: `backend/tests/test_conversation.py`, `frontend/tests/workflow-*.test.ts*`

## Deployment Preview

Deployment preview creates records, health-checks accessible artifacts, supports rollback records, and exposes clear failure states when container/cloud deployment runtimes are not available.

The Docker stack is for running the AgentHub app itself, not for claiming full production cloud deployment automation.

Key code:

- Backend: `backend/src/app/api/deployments.py`, `backend/src/app/services/deployments.py`
- Docker: `docker/`

## Security And Audit

Security operations include audit logs, roles, permissions, and user role updates. Sensitive operations should be routed through backend services and recorded where appropriate. API keys belong in backend configuration or model-provider records, not frontend code.

Key code:

- Backend: `backend/src/app/api/security_ops.py`, `backend/src/app/services/audit.py`, `backend/src/db/models/security.py`
- Frontend: `frontend/src/features/platform/components/SecurityOpsPanel.tsx`
