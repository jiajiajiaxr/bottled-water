from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.core.response import ok
from app.deps import get_current_user
from app.models import Conversation, Subtask, Task, User, utcnow
from app.schemas.common import ApiResponse
from app.services.serialization import subtask_to_dict, task_to_dict
from app.services.tasks.service import create_task_for_prompt
from db import get_db


router = APIRouter(tags=["tasks"])


class CreateTaskRequest(BaseModel):
    conversation_id: str
    title: str = ""
    description: str = ""
    prompt: str | None = None
    plan: dict[str, Any] | None = None


class ApproveSubtaskRequest(BaseModel):
    comment: str = ""


async def _get_conversation(db: AsyncSession, user: User, conversation_id: str) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation or conversation.creator_id != user.id:
        raise NotFoundError("Conversation not found")
    return conversation


async def _get_task(db: AsyncSession, user: User, task_id: str) -> Task:
    task = await db.get(Task, task_id)
    if not task:
        raise NotFoundError("Task not found")
    await _get_conversation(db, user, task.conversation_id)
    return task


@router.post("/tasks", response_model=ApiResponse[dict])
async def create_task(
    payload: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = await _get_conversation(db, user, payload.conversation_id)
    prompt = payload.prompt or payload.description or payload.title or "AgentHub task"
    task = await db.run_sync(
        lambda session: create_task_for_prompt(session, conversation, prompt, payload.plan)
    )
    if payload.title:
        task.title = payload.title
    if payload.description:
        task.description = payload.description
    await db.commit()
    return ok(task_to_dict(task), "Task created")


@router.get("/tasks", response_model=ApiResponse[list[dict]])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        await db.scalars(
            select(Task)
            .join(Conversation, Conversation.id == Task.conversation_id)
            .where(
                Conversation.creator_id == user.id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(Task.updated_at.desc(), Task.created_at.desc())
            .limit(100)
        )
    ).all()
    return ok([task_to_dict(task) for task in rows])


@router.get("/tasks/{task_id}/status", response_model=ApiResponse[dict])
async def get_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_task(db, user, task_id)
    return ok(task_to_dict(task))


@router.get("/tasks/{task_id}/subtasks", response_model=ApiResponse[list[dict]])
async def list_subtasks(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_task(db, user, task_id)
    subtasks = (
        await db.scalars(
            select(Subtask)
            .options(selectinload(Subtask.agent))
            .where(Subtask.parent_task_id == task.id)
            .order_by(Subtask.order_index, Subtask.created_at)
        )
    ).all()
    return ok([subtask_to_dict(item) for item in subtasks])


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse[dict])
async def cancel_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = await _get_task(db, user, task_id)
    if task.status not in {"COMPLETED", "FAILED", "CANCELLED"}:
        task.status = "CANCELLED"
        task.completed_at = utcnow()
    await db.commit()
    await db.refresh(task)
    return ok(task_to_dict(task), "Task cancelled")


@router.post("/subtasks/{subtask_id}/approve", response_model=ApiResponse[dict])
async def approve_subtask(
    subtask_id: str,
    payload: ApproveSubtaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    subtask = await db.get(Subtask, subtask_id)
    if not subtask:
        raise NotFoundError("Subtask not found")
    await _get_task(db, user, subtask.parent_task_id)
    subtask.status = "APPROVED"
    subtask.completed_at = utcnow()
    subtask.output = {**(subtask.output or {}), "approval_comment": payload.comment}
    await db.commit()
    await db.refresh(subtask, ["agent"])
    return ok(subtask_to_dict(subtask), "Subtask approved")
