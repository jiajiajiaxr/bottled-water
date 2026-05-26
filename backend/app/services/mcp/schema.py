from __future__ import annotations

from typing import Any

from app.models import McpServer
from app.services.mcp.transports import tool_name
from app.services.tools.schema import validate_tool_arguments


def validate_mcp_arguments(
    server: McpServer,
    name: str,
    arguments: dict[str, Any] | None,
) -> None:
    schema = _tool_schema(server, name)
    if schema:
        validate_tool_arguments(schema, arguments or {}, tool_name=f"mcp.{server.id}.{name}")


def _tool_schema(server: McpServer, name: str) -> dict[str, Any] | None:
    for tool in (server.tools or []):
        if not isinstance(tool, dict) or tool_name(tool) != name:
            continue
        for key in ("input_schema", "inputSchema", "parameters", "schema"):
            value = tool.get(key)
            if isinstance(value, dict):
                return value
    return None
