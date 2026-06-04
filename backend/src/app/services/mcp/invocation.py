from __future__ import annotations

import time
from inspect import isawaitable
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationAppError
from app.models import McpServer, McpToolInvocation, User, utcnow
from app.services.audit import write_audit_log
from app.services.mcp.schema import validate_mcp_arguments
from app.services.mcp.transports.common import tool_allowed
from app.services.mcp.transports.http import call_http_mcp
from app.services.mcp.transports.sse_ws import call_stream_mcp
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
    invocation = await _start_invocation(db, server, tool_name_value, arguments, user, conversation_id)
    started = time.perf_counter()
    try:
        _validate_invocation_request(server, tool_name_value, arguments)
        invocation.result = await _call_server(server, invocation, timeout_ms)
        invocation.status = "succeeded"
    except Exception as exc:
        _mark_invocation_failed(invocation, exc)
    await _finish_invocation(db, server, invocation, user, started)
    return mcp_invocation_to_dict(invocation)


def _validate_invocation_request(
    server: McpServer,
    tool_name_value: str,
    arguments: dict[str, Any] | None,
) -> None:
    if not server.enabled:
        raise ValidationAppError("MCP server is disabled")
    if not tool_allowed(server, tool_name_value):
        raise ForbiddenError("MCP tool is not allowed by server tools or tool_filter")
    validate_mcp_arguments(server, tool_name_value, arguments)


def _mark_invocation_failed(invocation: McpToolInvocation, exc: Exception) -> None:
    error_code = _error_code(exc)
    message = _error_message(exc, error_code)
    invocation.status = "failed"
    invocation.error_message = message
    invocation.result = {
        "error": message,
        "error_code": error_code,
        "tool_name": invocation.tool_name,
        "transport": invocation.transport,
    }
    invocation.extra = {
        **(invocation.extra or {}),
        "error_code": error_code,
        "error_type": exc.__class__.__name__,
    }


def _error_code(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, ForbiddenError):
        return "mcp_tool_not_allowed"
    if "disabled" in text:
        return "mcp_server_disabled"
    if "timed out" in text or "timeout" in text:
        return "mcp_timeout"
    if "authentication failed" in text or "http 401" in text or "http 403" in text:
        return "mcp_authentication_failed"
    if "unsupported mcp transport" in text:
        return "mcp_transport_unsupported"
    if "sse/websocket" in text or "not enabled in this runtime" in text:
        return "mcp_transport_unsupported"
    if "http" in text or '"status"' in text:
        return "mcp_transport_error"
    if "validation" in text or "required" in text or "schema" in text:
        return "mcp_argument_validation_failed"
    if isinstance(exc, ValidationAppError):
        return "mcp_argument_validation_failed"
    return "mcp_invocation_failed"


def _error_message(exc: Exception, error_code: str) -> str:
    text = str(exc)
    if error_code == "mcp_tool_not_allowed":
        return "MCP tool is not allowed by this server allowlist."
    if error_code == "mcp_server_disabled":
        return "MCP server is disabled."
    if error_code == "mcp_timeout":
        return text or "MCP tool invocation timed out."
    if error_code == "mcp_authentication_failed":
        return text or "MCP authentication failed. Check server headers or credentials."
    return text or "MCP tool invocation failed."


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


async def _start_invocation(
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
    await _maybe_await(db.flush())
    return invocation


async def _call_server(
    server: McpServer,
    invocation: McpToolInvocation,
    timeout_ms: int | None,
) -> dict[str, Any]:
    timeout = timeout_ms or min(server.timeout_ms or 30000, 5000)
    if server.transport == "httpStream":
        return await call_http_mcp(server, invocation, timeout)
    if server.transport in {"sse", "ws"}:
        return await call_stream_mcp(server, invocation, timeout)
    if server.transport == "stdio":
        return await call_stdio_mcp(server, invocation, timeout)
    raise ValidationAppError(f"unsupported MCP transport: {server.transport}")


async def _finish_invocation(
    db: Session,
    server: McpServer,
    invocation: McpToolInvocation,
    user: User | None,
    started: float,
) -> None:
    invocation.duration_ms = int((time.perf_counter() - started) * 1000)
    invocation.completed_at = utcnow()
    server.last_checked_at = utcnow()
    server.health_status = _server_health_after_invocation(invocation)
    if user:
        await _maybe_await(
            write_audit_log(
                db,
                user=user,
                action="mcp.invoke",
                target_type="mcp_server",
                target_id=server.id,
                detail={
                    "tool_name": invocation.tool_name,
                    "status": invocation.status,
                    "invocation_id": invocation.id,
                },
                risk_score=0.35 if invocation.status == "succeeded" else 0.6,
            )
        )
    await _maybe_await(db.flush())


def _server_health_after_invocation(invocation: McpToolInvocation) -> str:
    if invocation.status == "succeeded":
        return "online"
    error_code = str((invocation.extra or {}).get("error_code") or "")
    if error_code in {"mcp_tool_not_allowed", "mcp_argument_validation_failed"}:
        return "online"
    if error_code == "mcp_server_disabled":
        return "disabled"
    return "offline"
