from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.errors import ValidationAppError
from app.models import McpServer, McpToolInvocation


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
