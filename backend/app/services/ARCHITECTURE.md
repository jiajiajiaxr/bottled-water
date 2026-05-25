# AgentHub Backend Services

This directory is organized by service domain. The previous root-level service entrypoints have been removed; new code must import the domain modules directly.

## Dependency Direction

- `chat/` owns chat orchestration and may depend on `workflows/`, `agents/`, `tasks/`, and `realtime/`.
- `workflows/` owns workflow definition normalization, DAG ordering, planning, and `WorkflowRun` runtime state.
- `agents/` owns Agent execution, Function Call loops, context construction, and tool result feedback.
- `tools/` owns tool catalog, permission helpers, execution dispatch, built-in tools, and custom tool invocation.
- `realtime/` owns EventBus/SSE/WebSocket boundaries and must not depend on business orchestration modules.
- `tasks/` owns Task/Subtask creation and task plan serialization.

## Modules

- `chat/orchestrator.py`: chat orchestration entrypoint, including direct-agent routing and workflow-driven group execution.
- `chat/artifacts.py`: publishes artifact messages produced by tool execution.
- `workflows/definition.py`: workflow canvas normalization, node config, default canvas, DAG execution order, and workflow task plan generation.
- `workflows/planning.py`: task planning and workflow replanning prompts.
- `workflows/runtime.py`: `WorkflowRun.node_states` updates and conversation runtime synchronization.
- `agents/function_loop.py`: shared direct/group Agent Function Call loop. It creates assistant messages, streams model output, executes `tool_calls`, appends `role=tool` results, and asks the model for the final answer.
- `agents/direct.py`: direct single-Agent Task/Subtask lifecycle. The actual reasoning loop is delegated to `agents/function_loop.py`.
- `agents/tool_loop.py`: tool schema construction plus Skill/MCP/built-in tool execution dispatch. The older heuristic short loop remains only as an internal helper, not as a service entrypoint.
- `tools/registry.py`: built-in tool catalog, official Agent toolboxes, custom tools, and invocation dispatch.
- `tools/executor.py`: tool execution facade for future hard permission and schema validation.
- `tools/permissions.py`: tool permission name normalization helpers.
- `realtime/event_bus.py`: in-memory EventBus and event replay.
- `realtime/sse.py`: SSE channel helpers.
- `realtime/websocket.py`: WebSocket protocol helpers.
- `tasks/service.py`: create Task/Subtask records from a prompt and workflow plan.

## Root Entrypoints

Root-level orchestration/runtime/tool/event service modules have been deleted. Use the domain modules above directly.

## Extension Path

Multi-Agent Function Call workflow execution should start from `workflows/definition.py`, compile each `agent` node into an independent `agents/function_loop.py` execution unit, and write progress through `workflows/runtime.py`.

When adding concurrent node execution, pass IDs between tasks and create a fresh SQLAlchemy session per task. Do not share ORM objects across concurrent workers.
