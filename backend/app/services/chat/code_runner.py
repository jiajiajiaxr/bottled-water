from __future__ import annotations

from typing import Any

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.models import Conversation, Message, User
from app.services.tools.executor import invoke_tool
from app.services.workspaces.filesystem import (
    resolve_workspace_path,
    safe_segment,
    scoped_dir,
    workspace_id_from_conversation,
)


MAX_CHAT_CODE_LENGTH = 80_000
SUPPORTED_LANGUAGES = {"python", "py"}


def run_chat_python_code_block(
    db: Session,
    *,
    user: User,
    conversation: Conversation,
    message_id: str,
    block_index: int,
    code: str,
    language: str = "python",
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    """Persist a chat Python block into the conversation sandbox and run it."""

    _assert_conversation_access(user, conversation)
    message = _get_message(db, conversation.id, message_id)
    normalized_language = (language or "python").strip().lower()
    if normalized_language not in SUPPORTED_LANGUAGES:
        raise ValidationAppError("仅支持运行 Python 代码块")
    if block_index < 0:
        raise ValidationAppError("代码块序号无效")

    normalized_code = _normalize_code(code)
    workspace_id = workspace_id_from_conversation(db, conversation.id) or "default"
    sandbox_root = scoped_dir(workspace_id, "sandbox", conversation_id=conversation.id)
    filename = f"chat_code_{safe_segment(message.id)}_{block_index}.py"
    code_path = resolve_workspace_path(sandbox_root, filename)
    code_path.write_text(normalized_code, encoding="utf-8")

    execution = invoke_tool(
        db,
        user,
        "sandbox.run",
        {
            "workspace_id": workspace_id,
            "conversation_id": conversation.id,
            "message_id": message.id,
            "code_block_index": block_index,
            "source": "chat_code_block",
            "command": f"python {filename}",
            "timeout": timeout_seconds,
        },
    )
    result = execution.get("result") or {}
    payload = {
        "message_id": message.id,
        "code_block_index": block_index,
        "language": "python",
        "filename": filename,
        "sandbox_path": filename,
        "invocation_id": execution.get("invocation_id"),
        "status": result.get("status") or "failed",
        "stdout": result.get("stdout") or "",
        "stderr": result.get("stderr") or "",
        "exit_code": result.get("exit_code"),
        "duration_ms": result.get("duration_ms"),
        "sandbox_id": result.get("sandbox_id"),
        "cwd": result.get("cwd"),
        "created_at": result.get("created_at"),
    }
    _record_message_run(message, block_index, payload)
    db.flush()
    return payload


def _assert_conversation_access(user: User, conversation: Conversation) -> None:
    if conversation.creator_id != user.id and user.role != "admin":
        raise ForbiddenError("没有权限访问该会话")


def _get_message(db: Session, conversation_id: str, message_id: str) -> Message:
    message = db.get(Message, message_id)
    if not message or message.conversation_id != conversation_id or message.deleted_at is not None:
        raise NotFoundError("消息不存在")
    return message


def _normalize_code(code: str) -> str:
    normalized = (code or "").replace("\x00", "").strip("\ufeff")
    if not normalized.strip():
        raise ValidationAppError("代码块不能为空")
    if len(normalized) > MAX_CHAT_CODE_LENGTH:
        raise ValidationAppError("代码块过长，无法直接运行")
    return normalized.rstrip() + "\n"


def _record_message_run(message: Message, block_index: int, payload: dict[str, Any]) -> None:
    content = dict(message.content or {})
    runs = dict(content.get("code_block_runs") or {})
    runs[str(block_index)] = payload
    content["code_block_runs"] = runs
    message.content = content
    flag_modified(message, "content")
