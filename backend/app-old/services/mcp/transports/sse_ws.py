from __future__ import annotations

from typing import Any

from app.core.errors import ValidationAppError


async def call_stream_mcp(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    raise ValidationAppError("SSE/WebSocket MCP transport is not enabled in this runtime")
