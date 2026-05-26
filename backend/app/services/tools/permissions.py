from __future__ import annotations

from typing import Any

from app.services.tools.registry import BUILTIN_TOOLS, normalize_tool_names


def allowed_builtin_tools(values: list[Any]) -> list[str]:
    """Normalize configured tool names and keep only registered builtins."""

    return [name for name in normalize_tool_names(values) if name in BUILTIN_TOOLS]
