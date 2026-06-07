from __future__ import annotations

from typing import Any

from app.models import WorkflowRun
from app.services.realtime.event_bus import event_bus
from app.services.serialization import workflow_run_to_dict


async def publish_workflow_event(channel: str, event_type: str, payload: dict[str, Any]) -> None:
    await event_bus.publish(channel, event_type, payload)


async def publish_run_updated(channel: str, run: WorkflowRun, node_id: str | None = None) -> None:
    payload: dict[str, Any] = workflow_run_to_dict(run)
    payload["run_id"] = run.id
    if node_id:
        payload["node_id"] = node_id
    await publish_workflow_event(channel, "workflow:run_updated", payload)
    if run.status in {"completed", "failed", "cancelled"}:
        await publish_workflow_event(channel, f"workflow:{run.status}", payload)


async def publish_node_event(
    channel: str,
    run: WorkflowRun,
    node_id: str,
    status: str,
    payload: dict[str, Any] | None = None,
) -> None:
    await publish_workflow_event(
        channel,
        "workflow:node_updated",
        {"run_id": run.id, "node_id": node_id, "status": status, **(payload or {})},
    )
    event_map = {
        "running": "workflow:node_started",
        "completed": "workflow:node_completed",
        "succeeded": "workflow:node_completed",
        "failed": "workflow:node_failed",
        "skipped": "workflow:node_skipped",
    }
    if status in event_map:
        await publish_workflow_event(
            channel,
            event_map[status],
            {"run_id": run.id, "node_id": node_id, "status": status, **(payload or {})},
        )
    await publish_run_updated(channel, run, node_id=node_id)


async def publish_tool_event(
    channel: str,
    run: WorkflowRun,
    node_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    await publish_workflow_event(
        channel,
        event_type,
        {"run_id": run.id, "node_id": node_id, **payload},
    )
