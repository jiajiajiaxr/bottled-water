from __future__ import annotations

import asyncio
import fnmatch
import json
import os
import shlex
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationAppError
from app.models import McpServer, McpToolInvocation, User, utcnow
from app.services.audit import write_audit_log
from app.services.serialization import mcp_invocation_to_dict


def tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("name") or tool.get("id") or tool.get("tool_name") or "").strip()


def tool_allowed(server: McpServer, name: str) -> bool:
    tools = server.tools or []
    if any(item.get("name") == name and item.get("enabled", True) for item in tools if isinstance(item, dict)):
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in (server.tool_filter or []))


def safe_env(env: dict[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in (env or {}).items()}


async def call_http_mcp(server: McpServer, invocation: McpToolInvocation, timeout_ms: int) -> dict[str, Any]:
    if not server.url:
        raise ValidationAppError("MCP HTTP service missing URL")
    payload = {
        "jsonrpc": "2.0",
        "id": invocation.id,
        "method": "tools/call",
        "params": {"name": invocation.tool_name, "arguments": invocation.arguments or {}},
    }
    async with httpx.AsyncClient(timeout=max(1, timeout_ms / 1000)) as client:
        response = await client.post(
            server.url.rstrip("/"),
            json=payload,
            headers={"Content-Type": "application/json", **(server.headers or {})},
        )
    try:
        data = response.json()
    except ValueError:
        data = {"text": response.text}
    if response.status_code < 200 or response.status_code >= 300:
        raise ValidationAppError(json.dumps({"status": response.status_code, "error": data}, ensure_ascii=False))
    return data if isinstance(data, dict) else {"result": data}


async def call_stdio_mcp(server: McpServer, invocation: McpToolInvocation, timeout_ms: int) -> dict[str, Any]:
    if not server.command:
        raise ValidationAppError("stdio MCP service missing command")
    command_parts = shlex.split(server.command, posix=os.name != "nt")
    argv = [*command_parts, *(server.args or [])]
    payload = {
        "jsonrpc": "2.0",
        "id": invocation.id,
        "method": "tools/call",
        "params": {"name": invocation.tool_name, "arguments": invocation.arguments or {}},
    }
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **safe_env(server.env or {})},
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
            timeout=max(1, timeout_ms / 1000),
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        raise ValidationAppError("stdio MCP tool invocation timed out") from exc
    text = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = {"stdout": text}
    if process.returncode not in {0, None}:
        raise ValidationAppError(json.dumps({"exit_code": process.returncode, "stdout": parsed, "stderr": err}, ensure_ascii=False))
    result = parsed if isinstance(parsed, dict) else {"result": parsed}
    if err:
        result.setdefault("stderr", err)
    return result


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
    timeout = timeout_ms or min(server.timeout_ms or 30000, 5000)
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
    start = time.perf_counter()
    try:
        if server.transport in {"httpStream", "sse", "ws"}:
            result = await call_http_mcp(server, invocation, timeout)
        elif server.transport == "stdio":
            result = await call_stdio_mcp(server, invocation, timeout)
        else:
            raise ValidationAppError(f"unsupported MCP transport: {server.transport}")
        invocation.status = "succeeded"
        invocation.result = result
    except Exception as exc:
        invocation.status = "failed"
        invocation.error_message = str(exc)
        invocation.result = {"error": str(exc)}
    invocation.duration_ms = int((time.perf_counter() - start) * 1000)
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
            detail={"tool_name": tool_name_value, "status": invocation.status, "invocation_id": invocation.id},
            risk_score=0.35 if invocation.status == "succeeded" else 0.6,
        )
    db.flush()
    return mcp_invocation_to_dict(invocation)
