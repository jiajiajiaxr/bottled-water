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
from app.models import Artifact, Conversation, FileAsset, Message, User, utcnow
from app.services.events import event_bus
from app.services.artifacts import build_demo_html, classify_artifact_request, create_artifact, create_preview_message
from app.services.orchestrator import run_orchestration
from app.services.serialization import artifact_to_dict, message_to_dict


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


def _send(db: Session, user: User, conversation_id: str, payload: dict, *, trigger_agent: bool = True) -> Message:
    conversation = _get_conversation(db, user, conversation_id)
    text = _message_text(payload).strip()
    if not text:
        raise ValidationAppError("消息内容不能为空")
    raw_content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    attachments = raw_content.get("attachments") or payload.get("attachments") or []
    normalized_attachments: list[dict] = []
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
        if file_asset:
            normalized_attachments.append(
                {
                    "file_id": file_asset.id,
                    "filename": file_asset.original_filename,
                    "content_type": file_asset.content_type,
                    "size": file_asset.size,
                    "parse_status": file_asset.parse_status,
                    "extracted_text": file_asset.extracted_text[:12000],
                }
            )
    message = Message(
        client_message_id=payload.get("client_message_id") or str(uuid.uuid4()),
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        content_type=payload.get("content_type") or "text",
        content={"text": text, "attachments": normalized_attachments},
        status="sent",
        reply_to_message_id=payload.get("reply_to_message_id") or payload.get("quotedMessageId"),
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
        previous = ORCHESTRATION_TASKS.get(conversation.id)
        if previous and not previous.done():
            previous.cancel()
        task = asyncio.create_task(run_orchestration(message.id))
        ORCHESTRATION_TASKS[conversation.id] = task
        task.add_done_callback(lambda done, cid=conversation.id: ORCHESTRATION_TASKS.pop(cid, None) if ORCHESTRATION_TASKS.get(cid) is done else None)
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
    preview_message = None
    artifact = None
    artifact_type = classify_artifact_request(message.content.get("text", ""))
    if artifact_type:
        conversation = db.get(Conversation, conversation_id)
        existing_preview = db.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.content_type == "preview_card",
                Message.created_at >= message.created_at,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.desc())
        )
        if not existing_preview and conversation:
            artifact_name = {
                "document": "AgentHub 文档产物预览",
                "spreadsheet": "AgentHub 表格产物预览",
                "slides": "AgentHub 演示文稿预览",
                "code": "AgentHub 代码产物预览",
                "web_app": "AgentHub Web 产物预览",
            }.get(artifact_type, "AgentHub 协作产物预览")
            artifact = create_artifact(
                db,
                conversation,
                task=None,
                name=artifact_name,
                html=build_demo_html(
                    message.content.get("text", ""),
                    "主控 Agent 正在生成最终说明，产物草稿已可先行预览。",
                    artifact_type=artifact_type,
                ),
                artifact_type=artifact_type,
            )
            preview_message = create_preview_message(db, conversation, artifact)
            conversation.last_message_preview = "已生成产物卡片，可点击后在右侧预览、编辑和部署。"
            conversation.last_message_sender = "Artifact Agent"
            conversation.last_message_at = utcnow()
            conversation.message_count += 1
            db.commit()
            db.refresh(artifact)
            db.refresh(preview_message)
        elif existing_preview:
            preview_message = existing_preview
            artifact_id = existing_preview.content.get("artifact_id") if isinstance(existing_preview.content, dict) else None
            artifact = db.get(Artifact, artifact_id) if artifact_id else None
    await event_bus.publish(f"conversation:{conversation_id}", "message:new", message_to_dict(message))
    if artifact:
        await event_bus.publish(f"conversation:{conversation_id}", "artifact:created", artifact_to_dict(artifact))
    if preview_message:
        await event_bus.publish(f"conversation:{conversation_id}", "message:new", message_to_dict(preview_message))
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
