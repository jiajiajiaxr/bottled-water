from __future__ import annotations

from app.models import Artifact, Conversation, Message
from app.services.artifact_exports import default_export_format


def create_preview_message(db, conversation: Conversation, artifact: Artifact) -> Message:
    tool_output = (artifact.content or {}).get("tool_output") or {}
    export_format = str(tool_output.get("format") or default_export_format(artifact))
    message = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=artifact.agent_id,
        sender_name="Master Agent",
        content_type="preview_card",
        content={
            "artifact_id": artifact.id,
            "title": artifact.name,
            "artifact_type": artifact.type,
            "preview_url": f"/api/v1/artifacts/{artifact.id}/preview",
            "export_url": f"/api/v1/artifacts/{artifact.id}/export?format={export_format}",
            "format": export_format,
            "filename": tool_output.get("filename"),
            "media_type": tool_output.get("media_type"),
            "file_count": len(artifact.content.get("files") or {}),
            "total_size": len((artifact.content.get("files") or {}).get("index.html", "")),
        },
        status="completed",
    )
    db.add(message)
    return message
