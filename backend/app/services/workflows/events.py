from __future__ import annotations

from typing import Any

from app.models import WorkflowRun
from app.services.realtime.event_bus import event_bus


async def publish_workflow_event(channel: str, event_type: str, payload: dict[str, Any]) -> None:
    await event_bus.publish(channel, event_type, payload)


async def publish_run_updated(channel: str, run: WorkflowRun, node_id: str | None = None) -> None:
    payload: dict[str, Any] = {"run_id": run.id, "status": run.status, "progress": run.progress}
    if node_id:
        payload["node_id"] = node_id
    await publish_workflow_event(channel, "workflow:run_updated", payload)


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
    await publish_run_updated(channel, run, node_id=node_id)
