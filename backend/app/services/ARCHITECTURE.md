# AgentHub Backend Services

This directory is organized by service domain. The previous root-level service entrypoints have been removed; new code must import the domain modules directly.

## Dependency Direction

- `chat/` owns chat orchestration and may depend on `workflows/`, `agents/`, `tasks/`, and `realtime/`.
- `workflows/` owns workflow graph validation, scheduling, node execution, planning, and `WorkflowRun` runtime state.
- `agents/` owns Agent execution, Function Call loops, context construction, and tool result feedback.
- `tools/` owns tool catalog, permission helpers, execution dispatch, built-in tools, and custom tool invocation.
- `realtime/` owns EventBus/SSE/WebSocket boundaries and must not depend on business orchestration modules.
- `tasks/` owns Task/Subtask creation and task plan serialization.

## Modules

- `chat/orchestrator.py`: chat orchestration entrypoint, including direct-agent routing and workflow-driven group execution.
- `chat/artifacts.py`: publishes artifact messages produced by tool execution.
- `workflows/definition.py`: workflow canvas normalization, node config, default canvas, DAG execution order, and workflow task plan generation.
- `workflows/graph.py`: Dify-style `WorkflowGraph`, `Node`, `Edge`, topological sorting, parallel levels, and branch target helpers.
- `workflows/engine.py`: workflow execution entrypoint used by group chat. It validates the graph, schedules nodes, persists runtime state, and delegates node execution.
- `workflows/scheduler.py`: serial, parallel-level, conditional-branch, and loop scheduling helpers.
- `workflows/planning.py`: task planning and workflow replanning prompts.
- `workflows/planner.py`: stable planner import surface for AI-generated or rearranged workflow canvases.
- `workflows/runtime.py`: `WorkflowRun`, `NodeRun`, and `EdgeRun` JSON-state helpers for node states, edge states, events, completion, cancel, skip, and retry metadata.
- `workflows/validator.py`: node type/config, edge, permission reference, loop limit, and cycle validation.
- `workflows/events.py`: workflow/node/tool SSE event publishing helpers.
- `workflows/nodes/`: node executors for `start`, `agent`, `tool`, `skill`, `mcp`, `condition`, `loop`, `review`, `artifact`, and `end`.
- `agents/function_loop.py`: shared direct/group Agent Function Call loop. It creates assistant messages, streams model output, executes `tool_calls`, appends `role=tool` results, and asks the model for the final answer.
- `agents/direct.py`: direct single-Agent Task/Subtask lifecycle. The actual reasoning loop is delegated to `agents/function_loop.py`.
- `agents/tool_loop.py`: Function Call tool schema construction plus Skill/MCP routing. The older heuristic short loop remains only as an internal helper, not as a service entrypoint.
- `tools/builtins/registry.py`: built-in tool metadata, JSON schemas, and official Agent toolboxes.
- `tools/builtins/executor.py`: built-in tool dispatch for file, artifact, runtime, QA, and deployment tools.
- `tools/builtins/artifact/`: artifact generation, storage, renderers, and export behavior.
- `tools/builtins/file/`: file extraction, conversion, preview, and file tool execution.
- `tools/builtins/sandbox/`: sandbox policy, command runner, and sandbox/test tool execution.
- `tools/catalog.py`: tool table bootstrap, custom tool visibility query, and unified catalog listing.
- `tools/custom.py`: custom Python tool runtime and invocation bookkeeping.
- `tools/executor.py`: unified tool execution entrypoint with schema validation and permission metadata checks.
- `tools/permissions.py`: tool name normalization and user permission helpers.
- `tools/schema.py`: lightweight JSON Schema argument validation for model-generated tool calls.
- `tools/registry.py`: compatibility re-export layer for older imports.
- `mcp/transports/`: HTTP, stdio, and reserved SSE/WebSocket MCP transport adapters.
- `skills/runners/`: prompt, Agent, MCP compatibility, and script Skill runner boundaries.
- `realtime/event_bus.py`: in-memory EventBus and event replay.
- `realtime/sse.py`: SSE channel helpers.
- `realtime/websocket.py`: WebSocket protocol helpers.
- `tasks/service.py`: create Task/Subtask records from a prompt and workflow plan.

## Root Entrypoints

Root-level orchestration/runtime/tool/event service modules have been deleted. Use the domain modules above directly.

## Extension Path

Multi-Agent Function Call workflow execution starts from `workflows/engine.py`. The workflow canvas is the source of truth; each `agent` or `review` node delegates to `agents/function_loop.py`, while tool-like nodes use their own executors under `workflows/nodes/`.

When adding concurrent node execution, pass IDs between tasks and create a fresh SQLAlchemy session per task. Do not share ORM objects across concurrent workers.
