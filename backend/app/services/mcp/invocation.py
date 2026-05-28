from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationAppError
from app.models import McpServer, McpToolInvocation, User, utcnow
from app.services.audit import write_audit_log
from app.services.mcp.schema import validate_mcp_arguments
from app.services.mcp.transports.common import tool_allowed
from app.services.mcp.transports.http import call_http_mcp
from app.services.mcp.transports.stdio import call_stdio_mcp
from app.services.serialization import mcp_invocation_to_dict


async def invoke_mcp_tool_recorded(
    db: Session,
    *,
    server: McpServer,
    tool_name_value: str,
    arguments: dict[str, Any] | None,
    user: User | None,
    conversation_id: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    if not server.enabled:
        raise ValidationAppError("MCP server is disabled")
    if not tool_allowed(server, tool_name_value):
        raise ForbiddenError("MCP tool is not allowed by server tools or tool_filter")
    validate_mcp_arguments(server, tool_name_value, arguments)
    invocation = _start_invocation(db, server, tool_name_value, arguments, user, conversation_id)
    started = time.perf_counter()
    try:
        invocation.result = await _call_server(server, invocation, timeout_ms)
        invocation.status = "succeeded"
    except Exception as exc:
        invocation.status = "failed"
        invocation.error_message = str(exc)
        invocation.result = {"error": str(exc)}
    _finish_invocation(db, server, invocation, user, started)
    return mcp_invocation_to_dict(invocation)


def _start_invocation(
    db: Session,
    server: McpServer,
    tool_name_value: str,
    arguments: dict[str, Any] | None,
    user: User | None,
    conversation_id: str | None,
) -> McpToolInvocation:
    invocation = McpToolInvocation(
        server_id=server.id,
        owner_id=user.id if user else server.owner_id,
        workspace_id=server.workspace_id,
        conversation_id=conversation_id,
        tool_name=tool_name_value,
        transport=server.transport,
        arguments=arguments or {},
        status="running",
        started_at=utcnow(),
    )
    db.add(invocation)
    db.flush()
    return invocation


async def _call_server(
    server: McpServer,
    invocation: McpToolInvocation,
    timeout_ms: int | None,
) -> dict[str, Any]:
    timeout = timeout_ms or min(server.timeout_ms or 30000, 5000)
    if server.transport in {"httpStream", "sse", "ws"}:
        return await call_http_mcp(server, invocation, timeout)
    if server.transport == "stdio":
        return await call_stdio_mcp(server, invocation, timeout)
    raise ValidationAppError(f"unsupported MCP transport: {server.transport}")


def _finish_invocation(
    db: Session,
    server: McpServer,
    invocation: McpToolInvocation,
    user: User | None,
    started: float,
) -> None:
    invocation.duration_ms = int((time.perf_counter() - started) * 1000)
    invocation.completed_at = utcnow()
    server.last_checked_at = utcnow()
    server.health_status = "online" if invocation.status == "succeeded" else "offline"
    if user:
        write_audit_log(
            db,
            user=user,
            action="mcp.invoke",
            target_type="mcp_server",
            target_id=server.id,
            detail={"tool_name": invocation.tool_name, "status": invocation.status, "invocation_id": invocation.id},
            risk_score=0.35 if invocation.status == "succeeded" else 0.6,
        )
    db.flush()
