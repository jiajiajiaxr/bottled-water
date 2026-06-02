from __future__ import annotations

import logging
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message, Task, WorkflowRun, utcnow
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict, task_to_dict
from app.services.workflows.runtime import _sync_workflow_run

logger = logging.getLogger(__name__)

TerminalStatus = Literal["completed", "failed", "cancelled"]


async def finalize_streaming_agent_messages(
    db: Session,
    *,
    conversation: Conversation,
    channel: str,
    status: TerminalStatus,
    stop_reason: str,
    fallback_text: str,
) -> int:
    """Close assistant bubbles that were left streaming by an interrupted run."""
    messages = db.scalars(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.sender_type == "agent",
            Message.status == "streaming",
            Message.deleted_at.is_(None),
        )
    ).all()
    if not messages:
        return 0

    for message in messages:
        content = dict(message.content or {})
        text = str(content.get("text") or "").strip()
        content["text"] = text or fallback_text
        message.content = content
        message.status = status

    db.commit()

    for message in messages:
        await event_bus.publish(channel, "message:updated", message_to_dict(message))
        await event_bus.publish(
            channel,
            "message_stop",
            {
                "agent_message_id": message.id,
                "agent_id": message.sender_id,
                "agent_name": message.sender_name,
                "stop_reason": stop_reason,
            },
        )
    return len(messages)


async def fail_generation(
    db: Session,
    *,
    conversation: Conversation | None,
    channel: str | None,
    task: Task | None,
    workflow_run: WorkflowRun | None,
    reason: str,
    error: Exception,
) -> None:
    """Persist a failed generation state and emit terminal SSE events."""
    logger.exception("chat generation failed: reason=%s error=%s", reason, error)
    if task:
        task.status = "FAILED"
        task.progress = min(max(task.progress or 0, 95), 100)
        task.error_info = {"reason": reason, "error": str(error)}
        task.completed_at = utcnow()
    if workflow_run:
        workflow_run.status = "failed"
        workflow_run.completed_at = utcnow()
        workflow_run.events = [
            *(workflow_run.events or []),
            {"type": "run.failed", "at": utcnow().isoformat(), "reason": reason, "error": str(error)},
        ][-300:]
        if conversation:
            _sync_workflow_run(conversation, workflow_run)
    if conversation:
        conversation.last_message_preview = "本轮响应异常结束，已停止生成。"
        conversation.last_message_sender = "AgentHub"
        conversation.last_message_at = utcnow()
    db.commit()

    if not conversation or not channel:
        return

    await finalize_streaming_agent_messages(
        db,
        conversation=conversation,
        channel=channel,
        status="failed",
        stop_reason="generation_failed",
        fallback_text="本轮响应异常结束，已停止生成。",
    )
    if task:
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    if workflow_run:
        await event_bus.publish(
            channel,
            "workflow:run_updated",
            {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress},
        )
    await event_bus.publish(
        channel,
        "generation_finished",
        {"conversation_id": conversation.id, "reason": reason, "status": "failed"},
    )
