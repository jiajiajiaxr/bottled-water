from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.core.database import get_db
from app.core.errors import NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import Conversation, FileAsset, Message, User, utcnow
from app.services.context.attachments import readable_attachment_text
from app.services.chat.orchestrator import run_orchestration
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict


router = APIRouter(tags=["messages"])
compat_router = APIRouter(tags=["messages-compat"])
ORCHESTRATION_TASKS: dict[str, asyncio.Task] = {}


async def _payload(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _get_conversation(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.creator_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    return conversation


def _message_text(payload: dict) -> str:
    content = payload.get("content")
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    if isinstance(content, str):
        return content
    return str(payload.get("prompt") or "")


def _list_messages(db: Session, user: User, conversation_id: str) -> list[dict]:
    _get_conversation(db, user, conversation_id)
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc())
    ).all()
    return [message_to_dict(message) for message in messages]


def _normalize_attachments(db: Session, user: User, payload: dict) -> list[dict]:
    raw_content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    attachments = raw_content.get("attachments") or payload.get("attachments") or []
    normalized: list[dict] = []
    for item in attachments:
        file_id = item.get("file_id") or item.get("id") if isinstance(item, dict) else str(item)
        if not file_id:
            continue
        file_asset = db.scalar(
            select(FileAsset).where(
                FileAsset.id == file_id,
                FileAsset.owner_id == user.id,
                FileAsset.deleted_at.is_(None),
            )
        )
        if not file_asset:
            continue
        normalized.append(
            {
                "file_id": file_asset.id,
                "filename": file_asset.original_filename,
                "content_type": file_asset.content_type,
                "size": file_asset.size,
                "parse_status": file_asset.parse_status,
                "extracted_text": readable_attachment_text(
                    {
                        "content_type": file_asset.content_type,
                        "extracted_text": file_asset.extracted_text,
                        "metadata": file_asset.extra or {},
                    }
                )[:12000],
                "metadata": file_asset.extra or {},
            }
        )
    return normalized


def _schedule_orchestration(conversation_id: str, message_id: str) -> None:
    previous = ORCHESTRATION_TASKS.get(conversation_id)
    if previous and not previous.done():
        previous.cancel()
    task = asyncio.create_task(run_orchestration(message_id))
    ORCHESTRATION_TASKS[conversation_id] = task
    task.add_done_callback(
        lambda done, cid=conversation_id: ORCHESTRATION_TASKS.pop(cid, None)
        if ORCHESTRATION_TASKS.get(cid) is done
        else None
    )


def _send(db: Session, user: User, conversation_id: str, payload: dict, *, trigger_agent: bool = True) -> Message:
    conversation = _get_conversation(db, user, conversation_id)
    text = _message_text(payload).strip()
    if not text:
        raise ValidationAppError("消息内容不能为空")
    message = Message(
        client_message_id=payload.get("client_message_id") or str(uuid.uuid4()),
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        content_type=payload.get("content_type") or "text",
        content={"text": text, "attachments": _normalize_attachments(db, user, payload)},
        status="sent",
        reply_to_message_id=payload.get("reply_to_message_id") or payload.get("quotedMessageId"),
        extra={"thinking_enabled": bool(payload.get("thinking_enabled"))},
    )
    conversation.last_message_preview = text[:300]
    conversation.last_message_sender = user.display_name
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 5)
    conversation.message_count += 1
    db.add(message)
    db.commit()
    db.refresh(message)
    if trigger_agent:
        _schedule_orchestration(conversation.id, message.id)
    return message


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok({"items": _list_messages(db, user, conversation_id), "next_cursor": None, "has_more": False})


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    message = _send(db, user, conversation_id, await _payload(request), trigger_agent=True)
    await event_bus.publish(f"conversation:{conversation_id}", "message:new", message_to_dict(message))
    return ok(message_to_dict(message), "消息发送成功")


@router.post("/conversations/{conversation_id}/messages/{message_id}/regenerate")
async def regenerate_message(
    conversation_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    original = db.get(Message, message_id)
    if not original:
        raise NotFoundError("消息不存在")
    prompt = f"请重新生成：{original.content.get('text', '')}"
    message = _send(
        db,
        user,
        conversation_id,
        {"client_message_id": str(uuid.uuid4()), "content": {"text": prompt}},
        trigger_agent=True,
    )
    return ok(
        {
            "original_message_id": message_id,
            "new_message_id": message.id,
            "status": "generating",
            "stream_url": f"/api/v1/conversations/{conversation_id}/stream",
        },
        "已触发重新生成",
    )


@router.post("/conversations/{conversation_id}/messages/{message_id}/reply")
async def reply_message(
    conversation_id: str,
    message_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = await _payload(request)
    payload["reply_to_message_id"] = message_id
    message = _send(db, user, conversation_id, payload, trigger_agent=True)
    return ok(message_to_dict(message), "回复成功")


@router.get("/conversations/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: str,
    replay: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_conversation(db, user, conversation_id)

    async def generator():
        async for event in event_bus.subscribe(f"conversation:{conversation_id}", replay=replay):
            yield event.as_sse()

    return EventSourceResponse(generator())


@router.post("/conversations/{conversation_id}/stream/cancel")
async def cancel_stream(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation = _get_conversation(db, user, conversation_id)
    task = ORCHESTRATION_TASKS.get(conversation.id)
    cancelled = False
    if task and not task.done():
        task.cancel()
        cancelled = True
    await event_bus.publish(
        f"conversation:{conversation.id}",
        "generation:cancelled",
        {"conversation_id": conversation.id, "cancelled": cancelled},
    )
    return ok({"conversation_id": conversation.id, "cancelled": cancelled}, "Generation cancelled")


@compat_router.get("/conversations/{conversation_id}/messages")
async def compat_list_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _list_messages(db, user, conversation_id)


@compat_router.post("/conversations/{conversation_id}/messages")
async def compat_send_message(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    message = _send(db, user, conversation_id, await _payload(request), trigger_agent=False)
    return message_to_dict(message)
