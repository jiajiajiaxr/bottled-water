from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Conversation, Message, utcnow
from app.services.artifacts import create_preview_message
from app.services.realtime.event_bus import event_bus
from app.services.serialization import artifact_to_dict, message_to_dict


async def _publish_tool_artifacts(db: Session, channel: str, tool_context: dict[str, Any]) -> None:
    created_messages: list[Message] = []
    fallback_conversation_id = _conversation_id_from_channel(channel)
    tool_results = _collect_tool_results(tool_context)
    final_failed_tools = _final_failed_tool_names(tool_results)
    boundary_ids = _timeline_boundary_ids(tool_context)
    failed_tool_message_created = False
    for item in tool_results:
        output = item.get("output") if isinstance(item.get("output"), dict) else {}
        tool_name = str(item.get("tool_name") or output.get("tool") or "")
        if not output:
            continue
        await _publish_artifact_outputs(db, channel, output, tool_name=tool_name, boundary_ids=boundary_ids)
        if _should_show_tool_message(tool_name, output):
            if tool_name not in final_failed_tools:
                continue
            if failed_tool_message_created:
                continue
            failed_tool_message_created = True
        message = _message_for_tool_result(db, tool_name, output, fallback_conversation_id)
        if message:
            created_messages.append(message)
    if created_messages:
        db.commit()
        for message in created_messages:
            db.refresh(message)
            await event_bus.publish(channel, "message:new", message_to_dict(message))


async def _publish_artifact_outputs(
    db: Session,
    channel: str,
    output: dict[str, Any],
    *,
    tool_name: str = "",
    boundary_ids: list[str] | None = None,
) -> None:
    artifact_id = _artifact_id(output)
    artifact: Artifact | None = None
    if artifact_id:
        artifact = db.get(Artifact, artifact_id)
        if artifact:
            await event_bus.publish(channel, "artifact:created", artifact_to_dict(artifact))
    if artifact:
        preview = _preview_message_for_artifact_output(db, output, artifact, tool_name)
        if preview:
            _attach_timeline_boundary(preview, boundary_ids)
            preview.created_at = utcnow()
            preview.updated_at = utcnow()
            db.commit()
            db.refresh(preview)
            await event_bus.publish(channel, "message:new", message_to_dict(preview))


def _preview_message_for_artifact_output(
    db: Session,
    output: dict[str, Any],
    artifact: Artifact,
    tool_name: str,
) -> Message | None:
    preview_message_id = output.get("preview_message_id")
    if preview_message_id:
        preview = db.get(Message, str(preview_message_id))
        if preview:
            return preview
    if not _is_artifact_create_output(tool_name, output):
        return None
    existing = db.scalars(
        select(Message)
        .where(
            Message.conversation_id == artifact.conversation_id,
            Message.content_type == "preview_card",
            Message.deleted_at.is_(None),
        )
        .order_by(Message.created_at.desc())
    ).all()
    for message in existing:
        content = message.content if isinstance(message.content, dict) else {}
        if content.get("artifact_id") == artifact.id:
            return message
    conversation = db.get(Conversation, artifact.conversation_id)
    if not conversation:
        return None
    preview = create_preview_message(db, conversation, artifact)
    db.commit()
    db.refresh(preview)
    return preview


def _is_artifact_create_output(tool_name: str, output: dict[str, Any]) -> bool:
    output_tool = str(output.get("tool") or "")
    return tool_name.startswith("artifact.create_") or output_tool.startswith("artifact.create_")


def _message_for_tool_result(
    db: Session,
    tool_name: str,
    output: dict[str, Any],
    fallback_conversation_id: str | None,
) -> Message | None:
    if tool_name.startswith("artifact.create_"):
        return None
    conversation_id = _conversation_id_from_output(db, output) or fallback_conversation_id
    if not conversation_id:
        return None
    if tool_name == "artifact.export" and output.get("export_url"):
        return _create_event_message(
            db,
            conversation_id,
            "Artifact Tool",
            f"导出已准备：{output.get('format') or 'artifact'}",
            {"tool_name": tool_name, **output},
        )
    if tool_name == "deploy.preview" and isinstance(output.get("deployment"), dict):
        deployment = output["deployment"]
        message = Message(
            conversation_id=conversation_id,
            sender_type="agent",
            sender_name="Deploy Agent",
            content_type="deploy_status_card",
            content={
                "deployment_id": deployment.get("id"),
                "status": deployment.get("status"),
                "deploy_url": deployment.get("url"),
                "steps": deployment.get("steps") or [],
                "tool_name": tool_name,
            },
            status="completed",
        )
        db.add(message)
        _touch_conversation(db, conversation_id, "部署预览已生成", "Deploy Agent")
        return message
    if _should_show_tool_message(tool_name, output):
        return _create_event_message(
            db,
            conversation_id,
            "Tool Runner",
            _tool_summary(tool_name, output),
            {"tool_name": tool_name, "output": _compact(output)},
        )
    return None


def _create_event_message(
    db: Session,
    conversation_id: str,
    sender_name: str,
    text: str,
    content: dict[str, Any],
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        sender_type="agent",
        sender_name=sender_name,
        content_type="event",
        content={"text": text, **content},
        status="completed",
    )
    db.add(message)
    _touch_conversation(db, conversation_id, text, sender_name)
    return message


def _touch_conversation(db: Session, conversation_id: str, preview: str, sender: str) -> None:
    from app.models import Conversation

    conversation = db.get(Conversation, conversation_id)
    if not conversation:
        return
    conversation.last_message_preview = preview[:300]
    conversation.last_message_sender = sender
    conversation.last_message_at = utcnow()
    conversation.message_count += 1


def _timeline_boundary_ids(tool_context: dict[str, Any]) -> list[str]:
    candidates = [
        tool_context.get("assistant_message_id"),
        tool_context.get("agent_message_id"),
        tool_context.get("user_message_id"),
        tool_context.get("trigger_message_id"),
        tool_context.get("client_message_id"),
    ]
    ids: list[str] = []
    for value in candidates:
        if isinstance(value, str) and value.strip() and value not in ids:
            ids.append(value)
    return ids


def _attach_timeline_boundary(preview: Message, boundary_ids: list[str] | None) -> None:
    if not boundary_ids:
        return
    content = dict(preview.content or {})
    existing = content.get("_streamHistoryBoundaryIds")
    merged: list[str] = []
    if isinstance(existing, list):
        merged.extend(str(value) for value in existing if isinstance(value, str) and value.strip())
    for value in boundary_ids:
        if value and value not in merged:
            merged.append(value)
    if merged:
        content["_streamHistoryBoundaryIds"] = merged
        preview.content = content


def _collect_tool_results(value: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if isinstance(value.get("output"), dict) and value.get("tool_name"):
            results.append(value)
        result = value.get("result")
        if isinstance(result, dict) and isinstance(result.get("output"), dict):
            results.append(result)
        for child in value.values():
            results.extend(_collect_tool_results(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(_collect_tool_results(child))
    return results


def _final_failed_tool_names(items: list[dict[str, Any]]) -> set[str]:
    final_by_tool: dict[str, dict[str, Any]] = {}
    for item in items:
        output = item.get("output") if isinstance(item.get("output"), dict) else {}
        tool_name = str(item.get("tool_name") or output.get("tool") or "")
        if tool_name:
            final_by_tool[tool_name] = output
    return {
        tool_name
        for tool_name, output in final_by_tool.items()
        if _should_show_tool_message(tool_name, output)
    }


def _artifact_id(output: dict[str, Any]) -> str | None:
    if output.get("artifact_id"):
        return str(output["artifact_id"])
    artifact = output.get("artifact")
    if isinstance(artifact, dict) and artifact.get("id"):
        return str(artifact["id"])
    return None


def _conversation_id_from_output(db: Session, output: dict[str, Any]) -> str | None:
    artifact_id = _artifact_id(output)
    if artifact_id:
        artifact = db.get(Artifact, artifact_id)
        return artifact.conversation_id if artifact else None
    if output.get("conversation_id"):
        return str(output["conversation_id"])
    return None


def _conversation_id_from_channel(channel: str) -> str | None:
    prefix = "conversation:"
    return channel.removeprefix(prefix) if channel.startswith(prefix) else None


def _should_show_tool_message(tool_name: str, output: dict[str, Any]) -> bool:
    return _is_failed_tool_output(output) and (
        tool_name.startswith(("file.", "sandbox.", "test.", "api.", "skill.", "mcp."))
        or tool_name in {"sandbox.run", "test.run", "api.test", "browser.preview"}
        or output.get("type") in {"skill", "mcp"}
    )


def _is_failed_tool_output(output: dict[str, Any]) -> bool:
    status = str(output.get("status") or output.get("state") or "").lower()
    if status in {"failed", "error", "cancelled", "timeout"}:
        return True
    if output.get("ok") is False or output.get("success") is False:
        return True
    return bool(output.get("error") or output.get("error_message"))


def _tool_summary(tool_name: str, output: dict[str, Any]) -> str:
    status = output.get("status") or "completed"
    if tool_name == "api.test":
        return f"API 测试 {status}：{output.get('status_code')}"
    if tool_name in {"sandbox.run", "test.run"}:
        return f"{tool_name} {status}，exit_code={_exit_code(output)}"
    if tool_name.startswith("file."):
        return f"{tool_name} {status}"
    return f"{tool_name or 'tool'} {status}"


def _exit_code(output: dict[str, Any]) -> Any:
    if output.get("exit_code") is not None:
        return output.get("exit_code")
    result = output.get("result")
    if isinstance(result, dict):
        return result.get("exit_code")
    return None


def _compact(value: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= 3000:
        return value
    return {"summary": text[:3000], "truncated": True}
