from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.errors import ValidationAppError
from app.models import McpServer, utcnow
from app.services.mcp.transports.common import tool_name
from app.services.mcp.transports.http import list_http_mcp_tools
from app.services.mcp.transports.stdio import list_stdio_mcp_tools


DEFAULT_DISCOVERED_TOOLS = [
    {"name": "file.read", "description": "读取工作区文件", "enabled": True},
    {"name": "browser.open", "description": "打开浏览器页面", "enabled": True},
    {"name": "sandbox.run", "description": "在沙箱执行命令", "enabled": True},
]


def import_server_manifest(source_type: str, source: str) -> dict[str, Any]:
    if source_type == "manifest_url":
        try:
            response = httpx.get(source, timeout=10)
            response.raise_for_status()
            manifest = response.json()
        except Exception as exc:
            raise ValidationAppError(f"MCP manifest 导入失败：{exc}") from exc
    else:
        try:
            manifest = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValidationAppError("MCP JSON 配置格式错误") from exc
    if not isinstance(manifest, dict):
        raise ValidationAppError("MCP 配置必须是 JSON Object")
    return manifest


def discover_server_tools(server: McpServer) -> list[dict[str, Any]]:
    tools = [item for item in (server.tools or []) if isinstance(item, dict) and tool_name(item)]
    if tools:
        return tools
    if server.tool_filter:
        return [
            {"name": item, "description": f"Allowed MCP tool pattern: {item}", "enabled": True}
            for item in server.tool_filter
        ]
    return [{**item, "enabled": item.get("enabled", True) and server.transport != "disabled"} for item in DEFAULT_DISCOVERED_TOOLS]


def probe_server(server: McpServer) -> McpServer:
    server.health_status = "online" if server.enabled else "disabled"
    server.last_checked_at = utcnow()
    server.tools = discover_server_tools(server)
    return server


async def probe_server_async(server: McpServer, *, timeout_ms: int | None = None) -> McpServer:
    """探测 MCP 服务并刷新工具目录。"""

    server.last_checked_at = utcnow()
    if not server.enabled:
        server.health_status = "disabled"
        _set_probe_metadata(server, "disabled", "server_disabled", "MCP server is disabled")
        return server
    try:
        tools, source = await _discover_transport_tools(server, timeout_ms or server.timeout_ms or 30000)
    except Exception as exc:
        fallback = _builtin_stdio_tools(server)
        if fallback:
            server.tools = fallback
            server.health_status = "online"
            _set_probe_metadata(server, "degraded", "builtin_stdio_adapter", str(exc))
            return server
        server.health_status = "offline"
        _set_probe_metadata(server, "failed", exc.__class__.__name__, str(exc))
        return server
    server.tools = _normalize_tools(tools)
    server.health_status = "online"
    _set_probe_metadata(server, "ok", source, "")
    return server


async def _discover_transport_tools(server: McpServer, timeout_ms: int) -> tuple[list[dict[str, Any]], str]:
    if server.transport == "httpStream":
        return await list_http_mcp_tools(server, timeout_ms), "http_tools_list"
    if server.transport == "stdio":
        builtin = _builtin_stdio_tools(server)
        if builtin:
            return builtin, "builtin_stdio_adapter"
        return await list_stdio_mcp_tools(server, timeout_ms), "stdio_tools_list"
    if server.transport in {"sse", "ws"}:
        raise ValidationAppError("SSE/WebSocket MCP discovery is not enabled in this runtime")
    raise ValidationAppError(f"unsupported MCP transport: {server.transport}")


def _normalize_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in tools:
        name = tool_name(item)
        if not name:
            continue
        tool = {
            "name": name,
            "description": str(item.get("description") or item.get("title") or ""),
            "enabled": bool(item.get("enabled", True)),
        }
        for key in ("input_schema", "inputSchema", "parameters"):
            if isinstance(item.get(key), dict):
                tool["input_schema"] = item[key]
                break
        normalized.append(tool)
    return normalized


def _builtin_stdio_tools(server: McpServer) -> list[dict[str, Any]]:
    if server.transport != "stdio" or server.command != "agenthub-mcp-filesystem":
        return []
    if server.tool_filter:
        return [
            {"name": item, "description": f"Allowed MCP tool pattern: {item}", "enabled": True}
            for item in server.tool_filter
        ]
    return [
        {"name": "file.read", "description": "读取工作区文件", "enabled": True},
        {"name": "file.write", "description": "写入工作区文件", "enabled": True},
    ]


def _set_probe_metadata(server: McpServer, status: str, source: str, error: str) -> None:
    metadata = dict(server.extra or {})
    metadata["last_probe"] = {
        "status": status,
        "source": source,
        "error": error,
        "checked_at": server.last_checked_at.isoformat().replace("+00:00", "Z")
        if server.last_checked_at
        else None,
        "tool_count": len(server.tools or []),
    }
    server.extra = metadata
