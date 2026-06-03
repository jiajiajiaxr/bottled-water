"""
Context API

上下文压缩功能，统一使用 model_provider 调用 LLM。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import Message, User
from app.services.model_config_resolver import create_provider_from_db

router = APIRouter(tags=["context"])


async def _model_provider(db: AsyncSession):
    return await create_provider_from_db(db)


@router.get("/conversations/{conversation_id}/context", response_model=dict)
async def get_context(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    messages = (
        await db.scalars(select(Message).where(Message.conversation_id == conversation_id))
    ).all()
    chars = sum(len(str(m.content)) for m in messages)
    return ok(
        {"message_count": len(messages), "estimated_tokens": chars // 3, "compression": "available"}
    )


@router.post("/conversations/{conversation_id}/context/compress", response_model=dict)
async def compress_context(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    messages = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(20)
        )
    ).all()
    text = "\n".join(str(m.content.get("text", "")) for m in messages)
    provider = await _model_provider(db)
    if not provider:
        return ok({"summary": f"[mock] 压缩上下文 {len(text)} 字", "usage": {}})

    try:
        result = await provider.chat(
            messages=[{"role": "user", "content": f"请简要总结以下对话内容：\n{text}"}],
            max_tokens=500,
        )
        return ok({"summary": result.content, "usage": result.usage or {}})
    except Exception as exc:
        return ok({"summary": f"[error] {exc}", "usage": {}})
