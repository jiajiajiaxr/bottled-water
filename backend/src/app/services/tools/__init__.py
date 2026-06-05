"""Tool domain package.

The concrete catalog/executor modules are intentionally imported lazily so
package import does not initialize builtin tool dispatchers and create cycles
with artifact services.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "BUILTIN_TOOLS",
    "BuiltinTool",
    "allowed_builtin_tools",
    "get_custom_tool",
    "get_official_toolbox",
    "invoke_builtin_tool",
    "invoke_tool",
    "list_tools",
    "normalize_tool_names",
]


def __getattr__(name: str) -> Any:
    if name in {"BUILTIN_TOOLS", "BuiltinTool", "get_official_toolbox"}:
        from app.services.tools.builtins import registry

        return getattr(registry, name)
    if name == "invoke_builtin_tool":
        from app.services.tools.builtins.executor import invoke_builtin_tool

        return invoke_builtin_tool
    if name in {"get_custom_tool", "list_tools"}:
        from app.services.tools import catalog

        return getattr(catalog, name)
    if name == "invoke_tool":
        from app.services.tools.executor import invoke_tool

        return invoke_tool
    if name in {"allowed_builtin_tools", "normalize_tool_names"}:
        from app.services.tools import permissions

        return getattr(permissions, name)
    raise AttributeError(name)
