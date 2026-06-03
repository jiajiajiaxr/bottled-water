import asyncio
import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.errors import NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import Conversation, FileAsset, Message, User, utcnow
from app.schemas.common import ApiResponse
from app.schemas.requests import SendMessagePayload
from app.events import SseSink
from app.events import app_event_bus as event_bus
from app.services.runtime_service import OrchestratorService
from app.services.serialization import message_to_dict


router = APIRouter(tags=["messages"])
compat_router = APIRouter(tags=["messages-compat"])
ORCHESTRATION_TASKS: dict[str, asyncio.Task] = {}


async def _get_conversation(db: AsyncSession, user: User, conversation_id: str) -> Conversation:
    conversation = await db.scalar(
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


async def _list_messages(db: AsyncSession, user: User, conversation_id: str) -> list[dict]:
    await _get_conversation(db, user, conversation_id)
    messages = (
        await db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.deleted_at.is_(None))
            .order_by(Message.created_at.asc())
        )
    ).all()
    return [message_to_dict(message) for message in messages]


async def _send(
    db: AsyncSession, user: User, conversation_id: str, payload: dict, *, trigger_agent: bool = True
) -> Message:
    conversation = await _get_conversation(db, user, conversation_id)
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

        file_asset = await db.scalar(
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
    # 调度策略：消息级 > 会话级 > 默认 tech_lead
    scheduling_strategy = payload.get("scheduling_strategy", "")
    if not scheduling_strategy and conversation.extra:
        scheduling_strategy = (conversation.extra or {}).get("scheduling_strategy", "tech_lead")
    scheduling_strategy = (
        scheduling_strategy if scheduling_strategy in ("tech_lead",) else "tech_lead"
    )

    # 如果消息指定了新策略，持久化到会话
    if payload.get("scheduling_strategy") and conversation.extra != {
        **(conversation.extra or {}),
        "scheduling_strategy": scheduling_strategy,
    }:
        conversation.extra = {
            **(conversation.extra or {}),
            "scheduling_strategy": scheduling_strategy,
        }

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
        extra={
            "thinking_enabled": bool(payload.get("thinking_enabled")),
            "scheduling_strategy": scheduling_strategy,
        },
    )

    conversation.last_message_preview = text[:300]
    conversation.last_message_sender = user.display_name
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 5)
    conversation.message_count += 1

    db.add(message)
    await db.commit()
    await db.refresh(message)

    if trigger_agent:
        previous = ORCHESTRATION_TASKS.get(conversation.id)

        if previous and not previous.done():
            previous.cancel()
        model_config_id = payload.get("model_config_id")
        task = asyncio.create_task(
            OrchestratorService.run(db, conversation, message, scheduling_strategy, model_config_id)
        )
        ORCHESTRATION_TASKS[conversation.id] = task

        task.add_done_callback(
            lambda done, cid=conversation.id: (
                ORCHESTRATION_TASKS.pop(cid, None) if ORCHESTRATION_TASKS.get(cid) is done else None
            )
        )

    return message


@router.get("/conversations/{conversation_id}/messages", response_model=ApiResponse[dict])
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(
        {
            "items": await _list_messages(db, user, conversation_id),
            "next_cursor": None,
            "has_more": False,
        }
    )


@router.post("/conversations/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: str,
    payload: SendMessagePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """标准 SSE 流式接口（deprecated，请使用 WebSocket /ws/conversations/{id}）。

    保留用于向后兼容，内部事件仅通过 SseSink 推送。
    """
    await _get_conversation(db, user, conversation_id)

    channel = f"conversation:{conversation_id}"

    # 处理重新生成
    message_payload: dict = {}

    if payload.regenerate_message_id:
        original = db.get(Message, payload.regenerate_message_id)
        prompt = f"请重新生成这条回复：{original.content.get('text', '')}" if original else ""
        message_payload = {
            "client_message_id": str(uuid.uuid4()),
            "content": {"text": prompt},
        }
    else:
        message_payload = payload.model_dump()

    # 保存用户消息并触发编排
    message = await _send(db, user, conversation_id, message_payload, trigger_agent=True)

    # 先推送用户消息事件（保留用于兼容）
    await event_bus.publish(channel, "message:new", message_to_dict(message))

    # 返回 SSE 流：仅监听 SseSink
    async def generator():
        queue = SseSink.get_queue_for(conversation_id)
        if queue is None:
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
                await asyncio.sleep(0.05)
                yield {
                    "event": event.type,
                    "data": json.dumps(event.payload, ensure_ascii=False),
                }
                if event.type in ("system.session_completed", "system.session_error"):
                    break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    return EventSourceResponse(generator())


@router.post("/conversations/{conversation_id}/stream/cancel", response_model=ApiResponse[dict])
async def cancel_stream(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """取消 generation（兼容 SSE 路径，同时影响 WebSocket 路径的 Session）。"""
    from app.services.conversation_session_manager import ConversationSessionManager

    conversation = await _get_conversation(db, user, conversation_id)

    # 1. 取消旧 SSE 路径的 task
    task = ORCHESTRATION_TASKS.get(conversation.id)
    cancelled = False
    if task and not task.done():
        task.cancel()
        cancelled = True

    # 2. 取消新 WebSocket 路径的 Session generation
    session_manager = ConversationSessionManager.get_instance()
    if session_manager.is_generation_running(conversation.id):
        await session_manager.cancel_generation(conversation.id)
        cancelled = True

    await event_bus.publish(
        f"conversation:{conversation.id}",
        "generation:cancelled",
        {"conversation_id": conversation.id, "cancelled": cancelled},
    )
    return ok({"conversation_id": conversation.id, "cancelled": cancelled}, "Generation cancelled")


# ---- compat routes (只保留列表，删除发送和流式) ----


@compat_router.get("/conversations/{conversation_id}/messages", response_model=list[dict])
async def compat_list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _list_messages(db, user, conversation_id)
