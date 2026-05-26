from __future__ import annotations

import asyncio
import fnmatch
import json
import os
import shlex
from typing import Any

import httpx

from app.core.errors import ValidationAppError
from app.models import McpServer, McpToolInvocation


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


def _parse_stdio_result(returncode: int | None, stdout: bytes, stderr: bytes) -> dict[str, Any]:
    text = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()
    try:
        parsed = json.loads(text) if text else {}
    except json.JSONDecodeError:
        parsed = {"stdout": text}
    if returncode not in {0, None}:
        raise ValidationAppError(json.dumps({"exit_code": returncode, "stdout": parsed, "stderr": err}, ensure_ascii=False))
    result = parsed if isinstance(parsed, dict) else {"result": parsed}
    if err:
        result.setdefault("stderr", err)
    return result
