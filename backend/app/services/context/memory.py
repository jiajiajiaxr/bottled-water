from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message, utcnow
from app.services.context.compression import estimate_tokens, trim_text


@dataclass
class MemoryContext:
    messages: list[dict[str, str]] = field(default_factory=list)
    summary: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


def load_conversation_memory(
    db: Session,
    conversation: Conversation,
    *,
    current_message_id: str | None = None,
    token_budget: int = 3000,
) -> MemoryContext:
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.asc())
    ).all()
    usable = [item for item in rows if _usable_message(item, current_message_id)]
    recent, old = _split_by_budget(usable, token_budget=token_budget)
    summary = _existing_summary(conversation)
    if old:
        summary = _persist_summary(conversation, old, previous=summary)
        db.flush()
    return MemoryContext(
        messages=[_message_to_chat(item) for item in recent],
        summary=summary,
        diagnostics={
            "message_count": len(usable),
            "recent_count": len(recent),
            "summarized_count": len(old),
        },
    )


def attachment_context(message: Message, *, max_chars: int = 12_000) -> str:
    attachments = (message.content or {}).get("attachments") or []
    if not attachments:
        return ""
    parts: list[str] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or item.get("file_id") or "attachment")
        content_type = str(item.get("content_type") or "")
        extracted = str(item.get("extracted_text") or "").strip()
        if extracted:
            parts.append(f"- {filename} ({content_type})\n{trim_text(extracted, max_chars=3000)}")
        elif content_type.startswith("image/"):
            parts.append(f"- {filename} ({content_type})：图片附件；当前未启用视觉解析，不能假装理解图片内容。")
        else:
            parts.append(f"- {filename} ({content_type})：未提取到可读文本。")
    return trim_text("\n\n".join(parts), max_chars=max_chars)


def _usable_message(message: Message, current_message_id: str | None) -> bool:
    if message.id == current_message_id:
        return False
    if message.status == "streaming":
        return False
    text = str((message.content or {}).get("text") or "").strip()
    return bool(text)


def _split_by_budget(messages: list[Message], *, token_budget: int) -> tuple[list[Message], list[Message]]:
    recent: list[Message] = []
    used = 0
    for message in reversed(messages):
        tokens = estimate_tokens((message.content or {}).get("text") or "")
        if recent and used + tokens > token_budget:
            break
        recent.append(message)
        used += tokens
    recent.reverse()
    recent_ids = {item.id for item in recent}
    old = [item for item in messages if item.id not in recent_ids]
    return recent, old


def _message_to_chat(message: Message) -> dict[str, str]:
    role = "assistant" if message.sender_type == "agent" else "user"
    name = message.sender_name or message.sender_type
    text = str((message.content or {}).get("text") or "")
    return {"role": role, "content": f"{name}: {text}"}


def _existing_summary(conversation: Conversation) -> str:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    context = extra.get("context") if isinstance(extra.get("context"), dict) else {}
    return str(context.get("summary") or "")


def _persist_summary(conversation: Conversation, messages: list[Message], *, previous: str) -> str:
    lines = [previous] if previous else []
    for message in messages[-40:]:
        speaker = message.sender_name or message.sender_type
        text = str((message.content or {}).get("text") or "")
        lines.append(f"{speaker}: {trim_text(text, max_chars=500)}")
    summary = trim_text("\n".join(lines), max_chars=8000)
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    conversation.extra = {
        **extra,
        "context": {
            **(extra.get("context") if isinstance(extra.get("context"), dict) else {}),
            "summary": summary,
            "summarized_message_count": len(messages),
            "updated_at": utcnow().isoformat(),
        },
    }
    return summary
