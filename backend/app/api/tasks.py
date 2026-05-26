from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_db
from app.core.errors import NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import Conversation, Subtask, Task, User, utcnow
from app.services.tasks.service import create_task_for_prompt
from app.services.realtime.event_bus import event_bus
from app.services.serialization import subtask_to_dict, task_to_dict


router = APIRouter(tags=["tasks"])
compat_router = APIRouter(tags=["tasks-compat"])


async def _payload(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _create_task(db: Session, user: User, payload: dict) -> Task:
    conversation_id = payload.get("conversation_id")
    prompt = payload.get("prompt") or payload.get("description") or payload.get("title")
    if not prompt:
        raise ValidationAppError("任务描述不能为空")
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.creator_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    task = create_task_for_prompt(db, conversation, prompt)
    task.status = "QUEUED"
    task.progress = 10
    db.commit()
    db.refresh(task)
    return task


def _get_task(db: Session, user: User, task_id: str) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.creator_id == user.id))
    if not task:
        raise NotFoundError("任务不存在")
    return task


@router.post("/tasks")
@router.post("/orchestrator/tasks")
async def create_task(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(task_to_dict(_create_task(db, user, await _payload(request))), "任务已创建")


@router.get("/tasks")
async def list_tasks(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    tasks = db.scalars(select(Task).where(Task.creator_id == user.id).order_by(Task.created_at.desc())).all()
    return ok([task_to_dict(task) for task in tasks])


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(task_to_dict(_get_task(db, user, task_id)))


@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = _get_task(db, user, task_id)
    subtasks = db.scalars(select(Subtask).where(Subtask.parent_task_id == task.id)).all()
    counts = {"total": len(subtasks), "completed": 0, "running": 0, "pending": 0, "failed": 0}
    for subtask in subtasks:
        status = subtask.status.lower()
        if status in {"completed", "done"}:
            counts["completed"] += 1
        elif status in {"executing", "running", "dispatched", "acknowledged"}:
            counts["running"] += 1
        elif status in {"failed", "error"}:
            counts["failed"] += 1
        else:
            counts["pending"] += 1
    percentage = int((counts["completed"] / counts["total"]) * 100) if counts["total"] else task.progress
    return ok({"task": task_to_dict(task), "progress": {**counts, "percentage": percentage}})


@router.get("/tasks/{task_id}/subtasks")
async def list_subtasks(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_task(db, user, task_id)
    subtasks = db.scalars(select(Subtask).where(Subtask.parent_task_id == task_id)).all()
    return ok([subtask_to_dict(item) for item in subtasks])


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    task = _get_task(db, user, task_id)
    task.status = "CANCELLED"
    task.completed_at = utcnow()
    db.commit()
    return ok(task_to_dict(task), "任务已取消")


@router.post("/tasks/{task_id}/retry")
async def retry_task(
    task_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = _get_task(db, user, task_id)
    payload = await _payload(request)
    task.status = "QUEUED"
    task.progress = min(task.progress or 0, 15)
    task.error_info = None
    task.output = {**(task.output or {}), "retry": {"switch_agent": bool(payload.get("switch_agent")), "at": utcnow().isoformat()}}
    db.commit()
    await event_bus.publish(f"task:{task.id}", "task:retried", task_to_dict(task))
    return ok(task_to_dict(task), "任务已重新排队")


@router.post("/subtasks/{subtask_id}/approve")
async def approve_subtask(
    subtask_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    subtask = db.get(Subtask, subtask_id)
    if not subtask:
        raise NotFoundError("子任务不存在")
    task = _get_task(db, user, subtask.parent_task_id)
    payload = await _payload(request)
    subtask.status = "APPROVED"
    subtask.output = {**(subtask.output or {}), "approval": {"approved_by": user.id, "comment": payload.get("comment"), "at": utcnow().isoformat()}}
    task.output = {**(task.output or {}), "last_approval": subtask.id}
    db.commit()
    return ok(subtask_to_dict(subtask), "子任务已审批通过")


@router.post("/subtasks/{subtask_id}/reject")
async def reject_subtask(
    subtask_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    subtask = db.get(Subtask, subtask_id)
    if not subtask:
        raise NotFoundError("子任务不存在")
    _get_task(db, user, subtask.parent_task_id)
    payload = await _payload(request)
    subtask.status = "REJECTED"
    subtask.output = {**(subtask.output or {}), "rejection": {"rejected_by": user.id, "reason": payload.get("reason"), "at": utcnow().isoformat()}}
    db.commit()
    return ok(subtask_to_dict(subtask), "子任务已驳回")


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    async def generator():
        async for event in event_bus.subscribe(f"task:{task_id}", replay=True):
            yield event.as_sse()

    return EventSourceResponse(generator())


@compat_router.post("/orchestrator/tasks")
async def compat_create_task(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return task_to_dict(_create_task(db, user, await _payload(request)))
