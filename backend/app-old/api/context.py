from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ok
from app.deps import get_current_user
from app.models import Message, User
from app.services.ark import ark_client


router = APIRouter(tags=["context"])


@router.get("/conversations/{conversation_id}/context")
async def get_context(
    conversation_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all()
    chars = sum(len(str(message.content)) for message in messages)
    return ok({"message_count": len(messages), "estimated_tokens": chars // 3, "compression": "available"})


@router.post("/conversations/{conversation_id}/context/compress")
async def compress_context(
    conversation_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    messages = db.scalars(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.desc()).limit(20)
    ).all()
    text = "\n".join(str(message.content.get("text", "")) for message in messages)
    result = await ark_client.responses(text, max_output_tokens=500)
    return ok({"summary": result.text, "usage": result.usage})

