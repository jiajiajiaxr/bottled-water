from __future__ import annotations

from typing import Any

from app.models import Conversation, WorkflowRun, utcnow
from app.services.workflows.graph import WorkflowGraph


def _sync_workflow_run(conversation: Conversation, run: WorkflowRun) -> None:
    conversation.extra = {
        **(conversation.extra or {}),
        "workflow_runtime": {
            "run_id": run.id,
            "status": run.status,
            "progress": run.progress,
            "node_states": run.node_states or [],
            "updated_at": utcnow().isoformat(),
        },
    }


def build_node_states(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    graph = WorkflowGraph.from_workflow(workflow)
    for node in graph.nodes:
        output: dict[str, Any] = {}
        if node.type == "condition":
            branches = node.config.get("branches") if isinstance(node.config.get("branches"), list) else ["true", "false"]
            output = {"expression": node.config.get("expression"), "matched_branch": branches[0] if branches else "default"}
        elif node.type == "loop":
            output = {"max_iterations": int(node.config.get("max_iterations") or 3), "current_iteration": 0}
        states.append(
            {
                "id": node.id,
                "title": node.title,
                "type": node.type,
                "role": node.role,
                "agent_id": node.agent_id,
                "config": node.config,
                "status": "queued",
                "input": {},
                "progress": 0,
                "output": output,
                "error": None,
                "started_at": None,
                "completed_at": None,
            }
        )
    return states


def build_edge_states(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [edge.to_state() for edge in WorkflowGraph.from_workflow(workflow).edges]


def append_run_event(run: WorkflowRun, event_type: str, payload: dict[str, Any] | None = None) -> None:
    run.events = [
        *(run.events or []),
        {"type": event_type, "at": utcnow().isoformat(), **(payload or {})},
    ][-300:]


def set_edge_state(run: WorkflowRun, source: str, target: str, status: str) -> None:
    states = list(run.edge_states or [])
    for state in states:
        if str(state.get("from")) == source and str(state.get("to")) == target:
            state["status"] = status
            state["updated_at"] = utcnow().isoformat()
            break
    run.edge_states = states


def mark_workflow_completed(conversation: Conversation, run: WorkflowRun, status: str = "completed") -> None:
    run.status = status
    run.progress = 100 if status == "completed" else run.progress
    run.completed_at = utcnow()
    append_run_event(run, f"run.{status}")
    _sync_workflow_run(conversation, run)


def _set_workflow_node_state(
    run: WorkflowRun,
    node_id: str,
    *,
    status: str,
    progress: int,
    input_data: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    message: str | None = None,
) -> None:
    states = list(run.node_states or [])
    now = utcnow().isoformat()
    for state in states:
        if state.get("id") != node_id:
            continue
        state["status"] = status
        state["progress"] = max(0, min(100, progress))
        if input_data is not None:
            state["input"] = input_data
        if output is not None:
            state["output"] = {**(state.get("output") or {}), **output}
        if error is not None:
            state["error"] = error
        elif status not in {"failed", "error"}:
            state.setdefault("error", None)
        if message:
            state["message"] = message
        if status in {"running", "reviewing"} and not state.get("started_at"):
            state["started_at"] = now
        if status in {"completed", "succeeded", "failed", "skipped"}:
            state["completed_at"] = now
        break
    run.node_states = states
    total = max(1, len(states))
    done = len([state for state in states if state.get("status") in {"completed", "succeeded", "skipped"}])
    if status == "failed":
        run.progress = max(run.progress or 0, int(done / total * 100))
    else:
        run.progress = int(done / total * 100) if status != "running" else max(run.progress or 0, progress)
