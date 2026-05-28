from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Message, Workspace, utcnow
from app.services.context.compression import estimate_tokens, trim_text
from app.services.context.group import SpeakerIdentity, format_group_message_content


RECENT_DIGEST_TURNS = 8
SENSITIVE_PATTERN = re.compile(r"(api[_-]?key|secret|password|token|私钥|密码|密钥)", re.I)
EXPLICIT_MEMORY_PATTERN = re.compile(r"(请记住|帮我记住|记住一下|长期记住|保存到长期记忆|以后都记住)")
TRANSIENT_PATTERN = re.compile(r"^(你好|hello|hi|在吗|谢谢|1\s*[+＋]\s*1|再加上|算一下)")


@dataclass
class MemoryContext:
    messages: list[dict[str, str]] = field(default_factory=list)
    recent_messages_text: str = ""
    recent_turns_digest: str = ""
    summary: str = ""
    workspace_memory: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


def load_conversation_memory(
    db: Session,
    conversation: Conversation,
    *,
    current_message_id: str | None = None,
    token_budget: int = 3000,
    speaker_identities: dict[str, SpeakerIdentity] | None = None,
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
        messages=[_message_to_chat(item, speaker_identities=speaker_identities) for item in recent],
        recent_messages_text=_recent_messages_text(recent),
        recent_turns_digest=recent_turns_digest(recent),
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


def maybe_capture_workspace_memory(db: Session, conversation: Conversation, message: Message) -> str:
    workspace_id = _workspace_id(conversation)
    if not workspace_id:
        return ""
    text = str((message.content or {}).get("text") or "").strip()
    if not should_remember_workspace_fact(text):
        return ""
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        return ""
    return write_workspace_memory(db, workspace, text, source_message_id=message.id)


def write_workspace_memory(
    db: Session,
    workspace: Workspace,
    text: str,
    *,
    source_message_id: str | None = None,
) -> str:
    item = {
        "text": trim_text(text, max_chars=800),
        "kind": _memory_kind(text),
        "source_message_id": source_message_id,
        "created_at": utcnow().isoformat(),
    }
    extra = workspace.extra if isinstance(workspace.extra, dict) else {}
    memory = extra.get("memory") if isinstance(extra.get("memory"), dict) else {}
    items = [entry for entry in memory.get("items", []) if isinstance(entry, dict)]
    if any(entry.get("text") == item["text"] for entry in items):
        return item["text"]
    workspace.extra = {**extra, "memory": {**memory, "items": [item, *items][:80]}}
    db.flush()
    return item["text"]


def workspace_memory_text(workspace: Workspace | None, *, max_chars: int = 6000) -> str:
    if not workspace or not isinstance(workspace.extra, dict):
        return ""
    memory = workspace.extra.get("memory") if isinstance(workspace.extra.get("memory"), dict) else {}
    items = [entry for entry in memory.get("items", []) if isinstance(entry, dict)]
    lines = [
        f"- [{entry.get('kind') or 'fact'}] {entry.get('text')}"
        for entry in items
        if entry.get("text")
    ]
    return trim_text("\n".join(lines), max_chars=max_chars)


def should_remember_workspace_fact(text: str) -> bool:
    clean = text.strip()
    if len(clean) < 8 or len(clean) > 1000:
        return False
    if "?" in clean or "？" in clean:
        return False
    if re.match(r"^(你知道|请问|能否|是否|可以|帮我|告诉我)", clean):
        return False
    if SENSITIVE_PATTERN.search(clean):
        return False
    if TRANSIENT_PATTERN.search(clean.lower()):
        return False
    return bool(EXPLICIT_MEMORY_PATTERN.search(clean))


def recent_turns_digest(messages: list[Message], *, max_turns: int = RECENT_DIGEST_TURNS) -> str:
    recent = messages[-max_turns * 2 :]
    if not recent:
        return ""
    user_intents: list[str] = []
    facts: list[str] = []
    pending: list[str] = []
    references: list[str] = []
    for message in recent:
        role = "用户" if message.sender_type == "user" else "助手"
        text = _message_text(message)
        if not text:
            continue
        if message.sender_type == "user":
            user_intents.append(trim_text(text, max_chars=180))
        if _looks_like_fact(text):
            facts.append(f"{role}: {trim_text(text, max_chars=220)}")
        if re.search(r"(继续|再加上|改一下|刚才|那个|还要|下一步|未完成|待办)", text):
            pending.append(f"{role}: {trim_text(text, max_chars=180)}")
        matches = re.findall(r"[\w\u4e00-\u9fff.-]{1,40}\s*(?:=|是|叫|为)\s*[\w\u4e00-\u9fff.-]{1,80}", text)
        matches.extend(re.findall(r"\d+(?:\.\d+)?", text))
        references.extend(matches[:6])
    sections = [
        ("最近用户意图", user_intents[-4:]),
        ("关键事实", facts[-6:]),
        ("省略指代/未完成事项", pending[-6:]),
        ("数值与实体引用", list(dict.fromkeys(references))[-12:]),
    ]
    lines = [f"{title}：\n" + "\n".join(f"- {item}" for item in values) for title, values in sections if values]
    return trim_text("\n".join(lines), max_chars=3000)


def _usable_message(message: Message, current_message_id: str | None) -> bool:
    if message.id == current_message_id:
        return False
    if message.sender_type == "system":
        return False
    if message.sender_type == "agent" and message.status == "streaming":
        return False
    return bool(_message_text(message))


def _split_by_budget(messages: list[Message], *, token_budget: int) -> tuple[list[Message], list[Message]]:
    recent: list[Message] = []
    used = 0
    max_recent_messages = RECENT_DIGEST_TURNS * 2
    for message in reversed(messages):
        tokens = estimate_tokens(_message_text(message))
        if len(recent) >= max_recent_messages:
            break
        if recent and used + tokens > token_budget:
            break
        recent.append(message)
        used += tokens
    recent.reverse()
    recent_ids = {item.id for item in recent}
    old = [item for item in messages if item.id not in recent_ids]
    return recent, old


def _message_to_chat(
    message: Message,
    *,
    speaker_identities: dict[str, SpeakerIdentity] | None = None,
) -> dict[str, str]:
    role = "assistant" if message.sender_type == "agent" else "user"
    content = _message_text(message)
    if speaker_identities:
        content = format_group_message_content(
            sender_type=message.sender_type,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            text=content,
            identities=speaker_identities,
        )
    return {"role": role, "content": content}


def _recent_messages_text(messages: list[Message]) -> str:
    return "\n\n".join(_message_block(message) for message in messages)


def _message_block(message: Message) -> str:
    role = "助手" if message.sender_type == "agent" else "用户"
    return (
        "【当前会话历史消息】\n"
        f"时间：{_message_time(message)}\n"
        f"角色：{role}\n"
        f"发送者：{message.sender_name or message.sender_type}\n"
        f"状态：{message.status}\n"
        f"内容：{_message_text(message)}"
    )


def _existing_summary(conversation: Conversation) -> str:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    context = extra.get("context") if isinstance(extra.get("context"), dict) else {}
    return str(context.get("summary") or "")


def _persist_summary(conversation: Conversation, messages: list[Message], *, previous: str) -> str:
    lines = [previous] if previous else []
    for message in messages[-40:]:
        speaker = message.sender_name or message.sender_type
        lines.append(f"{_message_time(message)} {speaker}: {trim_text(_message_text(message), max_chars=500)}")
    summary = trim_text("\n".join(line for line in lines if line), max_chars=8000)
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


def _message_text(message: Message) -> str:
    return str((message.content or {}).get("text") or "").strip()


def _message_time(message: Message) -> str:
    value = getattr(message, "created_at", None)
    if isinstance(value, datetime):
        return value.isoformat()
    return "unknown"


def _workspace_id(conversation: Conversation) -> str | None:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    value = extra.get("workspace_id") or extra.get("workspaceId")
    return str(value) if value else None


def _looks_like_fact(text: str) -> bool:
    return bool(re.search(r"(=|等于|是|叫|为|项目|目标|偏好|默认|版本|地址|名称)", text))


def _memory_kind(text: str) -> str:
    if "偏好" in text or "默认" in text:
        return "preference"
    if "目标" in text or "长期" in text:
        return "goal"
    if "项目" in text or "背景" in text:
        return "project_background"
    return "fact"
