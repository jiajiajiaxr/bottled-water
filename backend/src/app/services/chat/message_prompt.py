from __future__ import annotations

from typing import Any

from app.services.context.attachments import attachment_context_from_items
from db.models import Message


def runtime_prompt_for_message(message: Message) -> str:
    """构造发送给 agent_runtime 的用户输入。

    聊天区仍然只展示用户原始文本；运行时额外附加当前消息附件的摘要、
    file_id 和解析状态，避免新 runtime 只收到纯文本而误判“没有收到文件”。
    """
    content = message.content if isinstance(message.content, dict) else {}
    text = str(content.get("text") or "").strip()
    attachments = content.get("attachments") if isinstance(content.get("attachments"), list) else []
    if not attachments:
        return text

    attachment_context = attachment_context_from_items(attachments, max_chars=12_000)
    file_refs = _file_reference_lines(attachments)
    sections = [
        text or "请结合上传附件继续处理。",
        "## 当前消息附件",
    ]
    if file_refs:
        sections.append(file_refs)
    if attachment_context:
        sections.append(attachment_context)
    sections.append("请基于这些附件作答；如果附件无法解析，请说明具体原因，不要说没有收到文件。")
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
            lines.append(f"- {filename}：file_id={file_id}，parse_status={parse_status}")
    return "\n".join(lines)
