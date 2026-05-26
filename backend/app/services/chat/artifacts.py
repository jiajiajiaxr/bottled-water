from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Artifact, Message
from app.services.realtime.event_bus import event_bus
from app.services.serialization import artifact_to_dict, message_to_dict


async def _publish_tool_artifacts(db: Session, channel: str, tool_context: dict[str, Any]) -> None:
    for item in tool_context.get("executions") or []:
        output = item.get("output")
        if not isinstance(output, dict):
            continue
        artifact_payload = output.get("artifact")
        if isinstance(artifact_payload, dict) and artifact_payload.get("id"):
            artifact = db.get(Artifact, str(artifact_payload["id"]))
            if artifact:
                await event_bus.publish(channel, "artifact:created", artifact_to_dict(artifact))
        preview_message_id = output.get("preview_message_id")
        if preview_message_id:
            preview = db.get(Message, str(preview_message_id))
            if preview:
                await event_bus.publish(channel, "message:new", message_to_dict(preview))
