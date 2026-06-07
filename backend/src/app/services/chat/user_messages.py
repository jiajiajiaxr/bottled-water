from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.services.chat.mentions import normalize_agent_mentions, raw_agent_mentions
from app.services.chat.scheduling import persist_scheduling_strategy, resolve_scheduling_strategy
from app.services.files.attachments import attachment_from_file_asset, refresh_attachment_text_if_needed
from app.services.files.references import file_reference_text, resolve_file_reference_attachments
from db.models import Conversation, FileAsset, Message, User, utcnow


def message_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if isinstance(content, dict):
        return str(content.get("text") or content.get("content") or "")
    if isinstance(content, str):
        return content
    return str(payload.get("prompt") or "")


async def save_user_message(
    db: AsyncSession,
    *,
    user: User,
    conversation: Conversation,
    payload: dict[str, Any],
) -> Message:
    text = message_text(payload).strip()
    if not text:
        raise ValidationAppError("Message content cannot be empty")

    client_message_id = str(payload.get("client_message_id") or "").strip()
    if client_message_id:
        existing = await db.scalar(
            select(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.sender_type == "user",
                Message.client_message_id == client_message_id,
                Message.deleted_at.is_(None),
            )
            .order_by(Message.created_at.asc())
        )
        if existing:
            return existing

    raw_content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    attachments = raw_content.get("attachments") or payload.get("attachments") or []
    normalized_attachments: list[dict[str, Any]] = []

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
        if not file_asset:
            continue
        if file_asset.conversation_id and file_asset.conversation_id != conversation.id:
            continue
        if not file_asset.conversation_id:
            file_asset.conversation_id = conversation.id
        refresh_attachment_text_if_needed(file_asset)
        normalized_attachments.append(attachment_from_file_asset(file_asset))

    existing_file_ids = {str(item.get("file_id") or "") for item in normalized_attachments}
    reference_text = file_reference_text(
        text,
        raw_content.get("file_references") or payload.get("file_references"),
    )
    if reference_text:
        referenced = await db.run_sync(
            lambda session: resolve_file_reference_attachments(
                session,
                user=user,
                conversation=conversation,
                text=reference_text,
                existing_file_ids=existing_file_ids,
            )
        )
        normalized_attachments.extend(referenced)

    normalized_agent_mentions = await db.run_sync(
        lambda session: normalize_agent_mentions(
            session,
            conversation_id=conversation.id,
            mentions=raw_agent_mentions(payload, raw_content),
        )
    )

    scheduling_strategy = resolve_scheduling_strategy(conversation, payload.get("scheduling_strategy"))
    if payload.get("scheduling_strategy"):
        persist_scheduling_strategy(conversation, scheduling_strategy)

    message = Message(
        client_message_id=client_message_id or str(uuid.uuid4()),
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        sender_avatar_url=user.avatar_url,
        content_type=payload.get("content_type") or "text",
        content={
            "text": text,
            "attachments": normalized_attachments,
            "agent_mentions": normalized_agent_mentions,
        },
        status="sent",
        reply_to_message_id=payload.get("reply_to_message_id") or payload.get("quotedMessageId"),
        extra={
            "thinking_enabled": bool(payload.get("thinking_enabled")),
            "scheduling_strategy": scheduling_strategy,
            "model_config_id": payload.get("model_config_id"),
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
    return message
