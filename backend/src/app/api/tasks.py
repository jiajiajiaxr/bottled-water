from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_db
from app.core.errors import NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import Conversation, Subtask, Task, User, utcnow
from app.schemas.common import ApiResponse, SubtaskOut, TaskOut
from app.schemas.requests import CreateTaskRequest
from app.services.orchestrator import create_task_for_prompt
from app.events import app_event_bus as event_bus
from app.services.serialization import subtask_to_dict, task_to_dict


router = APIRouter(tags=["tasks"])
compat_router = APIRouter(tags=["tasks-compat"])


class RetryTaskRequest(BaseModel):
    switch_agent: bool = False


class ApproveSubtaskRequest(BaseModel):
    comment: str | None = None


class RejectSubtaskRequest(BaseModel):
    reason: str | None = None


async def _create_task(db: AsyncSession, user: User, payload: dict) -> Task:
    conversation_id = payload.get("conversation_id")
    prompt = payload.get("prompt") or payload.get("description") or payload.get("title")
    if not prompt:
        raise ValidationAppError("任务描述不能为空")
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.creator_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    task = await create_task_for_prompt(db, conversation, prompt)
    task.status = "QUEUED"
    task.progress = 10
    await db.commit()
    await db.refresh(task)
    return task


async def _get_task(db: AsyncSession, user: User, task_id: str) -> Task:
    task = await db.scalar(select(Task).where(Task.id == task_id, Task.creator_id == user.id))
    if not task:
        raise NotFoundError("任务不存在")
    return task


@router.post("/tasks", response_model=ApiResponse[TaskOut])
@router.post("/orchestrator/tasks", response_model=ApiResponse[TaskOut])
async def create_task(
    payload: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(task_to_dict(await _create_task(db, user, payload.model_dump())), "任务已创建")


@router.get("/tasks", response_model=ApiResponse[list[TaskOut]])
async def list_tasks(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tasks = (await db.scalars(select(Task).where(Task.creator_id == user.id).order_by(Task.created_at.desc()))).all()
    return ok([task_to_dict(task) for task in tasks])


@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskOut])
async def get_task(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return ok(task_to_dict(await _get_task(db, user, task_id)))


@router.get("/tasks/{task_id}/status", response_model=ApiResponse[dict])
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    task = await _get_task(db, user, task_id)
    subtasks = (await db.scalars(select(Subtask).where(Subtask.parent_task_id == task.id))).all()
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


@router.get("/tasks/{task_id}/subtasks", response_model=ApiResponse[list[SubtaskOut]])
async def list_subtasks(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _get_task(db, user, task_id)
    subtasks = (await db.scalars(select(Subtask).where(Subtask.parent_task_id == task_id))).all()
    return ok([subtask_to_dict(item) for item in subtasks])


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse[TaskOut])
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    task = await _get_task(db, user, task_id)
    task.status = "CANCELLED"
    task.completed_at = utcnow()
    await db.commit()
    return ok(task_to_dict(task), "任务已取消")


@router.post("/tasks/{task_id}/retry", response_model=ApiResponse[TaskOut])
async def retry_task(
    task_id: str,
    payload: RetryTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_task(db, user, task_id)
    task.status = "QUEUED"
    task.progress = min(task.progress or 0, 15)
    task.error_info = None
    task.output = {**(task.output or {}), "retry": {"switch_agent": payload.switch_agent, "at": utcnow().isoformat()}}
    await db.commit()
    await event_bus.publish(f"task:{task.id}", "task:retried", task_to_dict(task))
    return ok(task_to_dict(task), "任务已重新排队")


@router.post("/subtasks/{subtask_id}/approve", response_model=ApiResponse[SubtaskOut])
async def approve_subtask(
    subtask_id: str,
    payload: ApproveSubtaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    subtask = await db.get(Subtask, subtask_id)
    if not subtask:
        raise NotFoundError("子任务不存在")
    task = await _get_task(db, user, subtask.parent_task_id)
    subtask.status = "APPROVED"
    subtask.output = {**(subtask.output or {}), "approval": {"approved_by": user.id, "comment": payload.comment, "at": utcnow().isoformat()}}
    task.output = {**(task.output or {}), "last_approval": subtask.id}
    await db.commit()
    return ok(subtask_to_dict(subtask), "子任务已审批通过")


@router.post("/subtasks/{subtask_id}/reject", response_model=ApiResponse[SubtaskOut])
async def reject_subtask(
    subtask_id: str,
    payload: RejectSubtaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    subtask = await db.get(Subtask, subtask_id)
    if not subtask:
        raise NotFoundError("子任务不存在")
    await _get_task(db, user, subtask.parent_task_id)
    subtask.status = "REJECTED"
    subtask.output = {**(subtask.output or {}), "rejection": {"rejected_by": user.id, "reason": payload.reason, "at": utcnow().isoformat()}}
    await db.commit()
    return ok(subtask_to_dict(subtask), "子任务已驳回")


@router.get("/tasks/{task_id}/stream")
async def stream_task(task_id: str):
    async def generator():
        async for event in event_bus.subscribe(f"task:{task_id}", replay=True):
            yield event.as_sse()

    return EventSourceResponse(generator())


@compat_router.post("/orchestrator/tasks", response_model=TaskOut)
async def compat_create_task(
    payload: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return task_to_dict(await _create_task(db, user, payload.model_dump()))
