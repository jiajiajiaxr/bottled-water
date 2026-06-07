from __future__ import annotations

from typing import Any

from app.services.context.attachments import attachment_context_from_items
from db.models import Message


def runtime_prompt_for_message(message: Message) -> str:
    """Build the runtime prompt for a user message.

    The visible chat bubble keeps the user's original text. Runtime input adds
    selected Agent mentions and the current message attachments once, so routing
    and file context stay deterministic without polluting the chat bubble.
    """

    content = message.content if isinstance(message.content, dict) else {}
    text = str(content.get("text") or "").strip()
    attachments = content.get("attachments") if isinstance(content.get("attachments"), list) else []
    mentions = content.get("agent_mentions") if isinstance(content.get("agent_mentions"), list) else []
    mention_context = _agent_mention_lines(mentions)
    if not attachments and not mention_context:
        return text

    sections: list[str] = []
    if mention_context:
        sections.append(mention_context)
    sections.append(text or "请结合上传附件继续处理。")
    if attachments:
        attachment_context = attachment_context_from_items(attachments, max_chars=12_000)
        file_refs = _file_reference_lines(attachments)
        sections.append("## 当前消息附件")
        if file_refs:
            sections.append(file_refs)
        if attachment_context:
            sections.append(attachment_context)
        sections.append(
            "请基于这些附件作答；如果某个附件无法解析，请说明具体原因，不要说没有收到文件。"
        )
    return "\n\n".join(part for part in sections if part)


def _file_reference_lines(attachments: list[Any]) -> str:
    lines: list[str] = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        file_id = str(item.get("file_id") or item.get("id") or "").strip()
        filename = str(item.get("filename") or item.get("original_filename") or file_id or "附件")
        parse_status = str(item.get("parse_status") or "unknown")
        if file_id:
            lines.append(f"- {filename}: file_id={file_id}; parse_status={parse_status}")
    return "\n".join(lines)


def _agent_mention_lines(mentions: list[Any]) -> str:
    lines: list[str] = []
    for item in mentions:
        if not isinstance(item, dict):
            continue
        agent_id = str(item.get("agent_id") or "").strip()
        name = str(item.get("agent_name") or "").strip()
        if not agent_id or not name:
            continue
        lines.append(f"- @{name} (agent_id={agent_id})")
    if not lines:
        return ""
    return "\n".join(
        [
            "## Required Agent Mentions",
            *lines,
            "Routing requirement: every listed Agent must be scheduled to reply or state an opinion in this turn.",
        ]
    )
