from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.models import ToolDefinition, ToolInvocation, User, utcnow


def start_tool_invocation(
    db: Session,
    *,
    user: User | None,
    tool_name: str,
    tool_type: str,
    arguments: dict[str, Any],
    tool: ToolDefinition | None = None,
    conversation_id: str | None = None,
) -> tuple[ToolInvocation, float]:
    invocation = ToolInvocation(
        tool_id=tool.id if tool else None,
        owner_id=user.id if user else None,
        workspace_id=tool.workspace_id if tool else None,
        conversation_id=conversation_id,
        tool_name=tool_name,
        tool_type=tool_type,
        arguments=arguments,
        status="running",
        started_at=utcnow(),
    )
    db.add(invocation)
    db.flush()
    return invocation, time.perf_counter()


def finish_tool_invocation(
    invocation: ToolInvocation,
    started: float,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    invocation.status = status
    invocation.result = result or {}
    invocation.error_message = error
    invocation.duration_ms = int((time.perf_counter() - started) * 1000)
    invocation.completed_at = utcnow()
