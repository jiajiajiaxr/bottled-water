from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Message, Task, WorkflowRun, utcnow
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict, task_to_dict
from app.services.workflows.runtime import _sync_workflow_run

RUNNING_TASK_STATUSES = {
    "PENDING",
    "QUEUED",
    "EXECUTING",
    "RUNNING",
    "REVIEW_PENDING",
    "REVIEWING",
    "STREAMING",
}


async def cancel_conversation_generation(
    db: Session,
    conversation: Conversation,
    *,
    channel: str,
    task_cancelled: bool,
) -> dict[str, int | bool | str]:
    """Persist cancellation state and emit terminal chat events."""
    messages = _cancel_streaming_messages(db, conversation)
    tasks = _cancel_running_tasks(db, conversation)
    workflow_runs = _cancel_running_workflow_runs(db, conversation)

    conversation.last_message_preview = "已停止本次响应"
    conversation.last_message_sender = "AgentHub"
    conversation.last_message_at = utcnow()
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
                "stop_reason": "cancelled",
            },
        )

    for task in tasks:
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))

    for workflow_run in workflow_runs:
        await event_bus.publish(
            channel,
            "workflow:run_updated",
            {
                "run_id": workflow_run.id,
                "status": workflow_run.status,
                "progress": workflow_run.progress,
            },
        )

    await event_bus.publish(
        channel,
        "generation:cancelled",
        {"conversation_id": conversation.id, "cancelled": True},
    )
    await event_bus.publish(
        channel,
        "generation_finished",
        {"conversation_id": conversation.id, "reason": "cancelled", "status": "cancelled"},
    )
    return {
        "conversation_id": conversation.id,
        "cancelled": True,
        "task_cancelled": task_cancelled,
        "messages": len(messages),
        "tasks": len(tasks),
        "workflow_runs": len(workflow_runs),
    }


def _cancel_streaming_messages(db: Session, conversation: Conversation) -> list[Message]:
    messages = db.scalars(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.sender_type == "agent",
            Message.status == "streaming",
            Message.deleted_at.is_(None),
        )
    ).all()
    for message in messages:
        content = dict(message.content or {})
        content["text"] = str(content.get("text") or "").strip() or "已停止本次响应"
        content["_activeToolCalls"] = []
        message.content = content
        message.status = "cancelled"
    return messages


def _cancel_running_tasks(db: Session, conversation: Conversation) -> list[Task]:
    tasks = db.scalars(
        select(Task).where(
            Task.conversation_id == conversation.id,
            func.upper(Task.status).in_(RUNNING_TASK_STATUSES),
        )
    ).all()
    for task in tasks:
        task.status = "CANCELLED"
        task.progress = min(task.progress or 0, 95)
        task.completed_at = utcnow()
        task.output = {**(task.output or {}), "cancelled": True}
    return tasks


def _cancel_running_workflow_runs(db: Session, conversation: Conversation) -> list[WorkflowRun]:
    workflow_runs = db.scalars(
        select(WorkflowRun).where(
            WorkflowRun.conversation_id == conversation.id,
            func.lower(WorkflowRun.status) == "running",
        )
    ).all()
    for workflow_run in workflow_runs:
        workflow_run.status = "cancelled"
        workflow_run.completed_at = utcnow()
        workflow_run.events = [
            *(workflow_run.events or []),
            {"type": "run.cancelled", "at": utcnow().isoformat(), "reason": "user_cancelled"},
        ][-300:]
        _sync_workflow_run(conversation, workflow_run)
    return workflow_runs
