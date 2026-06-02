from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.errors import ValidationAppError
from app.models import McpServer, utcnow
from app.services.mcp.transports.common import tool_name


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
