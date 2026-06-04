"""Deprecated compatibility shim; use app.services.mcp.* modules."""

from __future__ import annotations

from app.services.mcp.invocation import invoke_mcp_tool_recorded
from app.services.mcp.transports.common import safe_env, tool_allowed, tool_name
from app.services.mcp.transports.http import call_http_mcp
from app.services.mcp.transports.sse_ws import call_stream_mcp
from app.services.mcp.transports.stdio import call_stdio_mcp

__all__ = [
    "call_http_mcp",
    "call_stdio_mcp",
    "call_stream_mcp",
    "invoke_mcp_tool_recorded",
    "safe_env",
    "tool_allowed",
    "tool_name",
]
