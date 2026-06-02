from __future__ import annotations

import fnmatch
from typing import Any

from app.models import McpServer


def tool_name(tool: dict[str, Any]) -> str:
    return str(tool.get("name") or tool.get("id") or tool.get("tool_name") or "").strip()


def tool_allowed(server: McpServer, name: str) -> bool:
    tools = server.tools or []
    if any(item.get("name") == name and item.get("enabled", True) for item in tools if isinstance(item, dict)):
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in (server.tool_filter or []))


def safe_env(env: dict[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in (env or {}).items()}
