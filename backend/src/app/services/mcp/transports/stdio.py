from __future__ import annotations

import asyncio
import json
import os
import shlex
from typing import Any

from app.core.errors import ValidationAppError
from app.models import McpServer, McpToolInvocation
from app.services.mcp.transports.common import safe_env


async def call_stdio_mcp(server: McpServer, invocation: McpToolInvocation, timeout_ms: int) -> dict[str, Any]:
    if not server.command:
        raise ValidationAppError("stdio MCP service missing command")
    command_parts = shlex.split(server.command, posix=os.name != "nt")
    payload = {
        "jsonrpc": "2.0",
        "id": invocation.id,
        "method": "tools/call",
        "params": {"name": invocation.tool_name, "arguments": invocation.arguments or {}},
    }
    process = await asyncio.create_subprocess_exec(
        *[*command_parts, *(server.args or [])],
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
    return _parse_stdio_result(process.returncode, stdout, stderr)


async def list_stdio_mcp_tools(server: McpServer, timeout_ms: int) -> list[dict[str, Any]]:
    if not server.command:
        raise ValidationAppError("stdio MCP service missing command")
    command_parts = shlex.split(server.command, posix=os.name != "nt")
    payload = {"jsonrpc": "2.0", "id": "agenthub-tools-list", "method": "tools/list", "params": {}}
    try:
        process = await asyncio.create_subprocess_exec(
            *[*command_parts, *(server.args or [])],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, **safe_env(server.env or {})},
        )
    except FileNotFoundError as exc:
        raise ValidationAppError(f"stdio MCP command not found: {server.command}") from exc
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
            timeout=max(1, timeout_ms / 1000),
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        raise ValidationAppError("stdio MCP tools/list timed out") from exc
    data = _parse_stdio_result(process.returncode, stdout, stderr)
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    tools = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(tools, list):
        raise ValidationAppError("stdio MCP tools/list response missing result.tools")
    return [item for item in tools if isinstance(item, dict)]


def _parse_stdio_result(returncode: int | None, stdout: bytes, stderr: bytes) -> dict[str, Any]:
    text = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = {"stdout": text}
    if returncode not in {0, None}:
        message = {"exit_code": returncode, "stdout": parsed, "stderr": err}
        raise ValidationAppError(json.dumps(message, ensure_ascii=False))
    result = parsed if isinstance(parsed, dict) else {"result": parsed}
    if err:
        result.setdefault("stderr", err)
    return result
