from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Conversation, Message, ToolInvocation, User
from app.services.tools.executor import invoke_tool


SUPPORTED_LANGUAGES = {
    "python": ("py", "python {path}"),
    "py": ("py", "python {path}"),
    "javascript": ("js", "node {path}"),
    "js": ("js", "node {path}"),
    "node": ("js", "node {path}"),
    "bash": ("sh", "bash {path}"),
    "sh": ("sh", "sh {path}"),
    "shell": ("sh", "sh {path}"),
}


def run_message_code_block(
    db: Session,
    *,
    user: User,
    conversation_id: str,
    message_id: str,
    language: str,
    code: str,
    index: int,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    conversation = _conversation(db, user, conversation_id)
    message = _message(db, conversation.id, message_id)
    normalized = _normalize_language(language)
    source = code.strip("\n")
    if not source.strip():
        raise ValidationAppError("代码块内容不能为空")

    extension, command_template = SUPPORTED_LANGUAGES[normalized]
    filename = f"chat_code_{message.id[:8]}_{max(index, 0)}.{extension}"
    common_args = {
        "workspace_id": _workspace_id(conversation),
        "conversation_id": conversation.id,
        "path": filename,
    }
    file_payload = invoke_tool(
        db,
        user,
        "file.write",
        {**common_args, "content": source},
    )
    command = command_template.format(path=file_payload["result"]["sandbox_path"])
    result = _interactive_rejection(normalized, source, command)
    if not result:
        result = _run_sandbox(db, user, conversation, command, timeout_seconds)
    result.update(
        {
            "language": normalized,
            "code_block_index": index,
            "filename": filename,
            "file_invocation_id": file_payload.get("invocation_id"),
        }
    )
    _persist_code_run(db, message, index, result)
    db.commit()
    return result


def _run_sandbox(
    db: Session,
    user: User,
    conversation: Conversation,
    command: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    try:
        payload = invoke_tool(
            db,
            user,
            "sandbox.run",
            {
                "workspace_id": _workspace_id(conversation),
                "conversation_id": conversation.id,
                "command": command,
                "timeout": max(1, min(timeout_seconds, 30)),
            },
        )
        result = dict(payload.get("result") or {})
        result["invocation_id"] = payload.get("invocation_id")
        return _normalize_result(result)
    except Exception as exc:
        invocation = _latest_sandbox_invocation(db, user, conversation.id)
        return _normalize_result(
            {
                "status": "failed",
                "command": command,
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
                "duration_ms": invocation.duration_ms if invocation else 0,
                "invocation_id": invocation.id if invocation else None,
            }
        )


def _interactive_rejection(language: str, source: str, command: str) -> dict[str, Any] | None:
    if language in {"python", "py"} and re.search(r"\binput\s*\(", source):
        return _normalize_result(
            {
                "status": "failed",
                "command": command,
                "stdout": "",
                "stderr": "当前聊天代码运行不支持交互式 input()，请改成固定测试数据后再运行。",
                "exit_code": -1,
                "duration_ms": 0,
                "invocation_id": None,
            }
        )
    return None


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    exit_code = result.get("exit_code")
    if exit_code is None:
        exit_code = -1
    try:
        exit_code = int(exit_code)
    except (TypeError, ValueError):
        exit_code = -1
    status = str(result.get("status") or ("succeeded" if exit_code == 0 else "failed"))
    return {
        "status": status,
        "command": str(result.get("command") or ""),
        "stdout": str(result.get("stdout") or ""),
        "stderr": str(result.get("stderr") or result.get("error") or ""),
        "exit_code": exit_code,
        "duration_ms": int(result.get("duration_ms") or 0),
        "invocation_id": result.get("invocation_id"),
    }


def _persist_code_run(db: Session, message: Message, index: int, result: dict[str, Any]) -> None:
    content = dict(message.content or {})
    code_runs = dict(content.get("code_runs") or {})
    code_runs[str(index)] = result
    content["code_runs"] = code_runs
    message.content = content
    db.add(message)


def _conversation(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    if conversation.creator_id != user.id and user.role != "admin":
        raise ForbiddenError("无权访问该会话")
    return conversation


def _message(db: Session, conversation_id: str, message_id: str) -> Message:
    message = db.scalar(
        select(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
        )
    )
    if not message:
        raise NotFoundError("消息不存在")
    return message


def _normalize_language(language: str) -> str:
    normalized = (language or "").strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValidationAppError("当前只支持运行 Python、JavaScript 和 Bash 代码块")
    return normalized


def _workspace_id(conversation: Conversation) -> str | None:
    if isinstance(conversation.extra, dict):
        value = conversation.extra.get("workspace_id") or conversation.extra.get("workspaceId")
        return str(value) if value else None
    return None


def _latest_sandbox_invocation(
    db: Session,
    user: User,
    conversation_id: str,
) -> ToolInvocation | None:
    return db.scalar(
        select(ToolInvocation)
        .where(
            ToolInvocation.owner_id == user.id,
            ToolInvocation.conversation_id == conversation_id,
            ToolInvocation.tool_name == "sandbox.run",
        )
        .order_by(ToolInvocation.created_at.desc())
    )
