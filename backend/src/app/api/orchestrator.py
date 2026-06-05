from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.deps import get_current_user
from app.schemas.requests import CreateTaskRequest
from app.services.serialization import task_to_dict
from app.services.tasks.service import create_task_for_prompt
from db import get_db
from db.models import Conversation, User


router = APIRouter(tags=["orchestrator"])
compat_router = APIRouter(tags=["orchestrator-compat"])


async def _create_orchestrator_task(
    db: AsyncSession,
    user: User,
    payload: CreateTaskRequest,
) -> dict:
    if not payload.conversation_id:
        raise ValidationAppError("conversation_id 不能为空")
    prompt = (payload.prompt or payload.title or payload.description or "").strip()
    if not prompt:
        raise ValidationAppError("prompt 不能为空")

    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.creator_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")

    task = await db.run_sync(lambda session: create_task_for_prompt(session, conversation, prompt))
    await db.commit()
    await db.refresh(task)
    body = task_to_dict(task)
    body["task_id"] = task.id
    return body


@router.post("/orchestrator/tasks")
async def create_task(
    payload: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _create_orchestrator_task(db, user, payload)


@compat_router.post("/orchestrator/tasks")
async def create_task_compat(
    payload: CreateTaskRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _create_orchestrator_task(db, user, payload)
