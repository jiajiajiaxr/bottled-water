from __future__ import annotations

from typing import Any

from app.models import Conversation, WorkflowRun, utcnow


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


def _set_workflow_node_state(run: WorkflowRun, node_id: str, *, status: str, progress: int, output: dict[str, Any] | None = None, message: str | None = None) -> None:
    states = list(run.node_states or [])
    now = utcnow().isoformat()
    for state in states:
        if state.get("id") != node_id:
            continue
        state["status"] = status
        state["progress"] = max(0, min(100, progress))
        if output is not None:
            state["output"] = {**(state.get("output") or {}), **output}
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
    run.progress = int(done / total * 100) if status != "running" else max(run.progress or 0, progress)
