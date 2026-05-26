from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services.tools.builtin_executor import invoke_builtin_tool
from app.services.tools.builtins import BUILTIN_TOOLS
from app.services.tools.catalog import ensure_tool_tables, get_custom_tool
from app.services.tools.custom import invoke_custom_tool
from app.services.tools.permissions import check_user_tool_permissions
from app.services.tools.schema import validate_tool_arguments


def invoke_tool(
    db: Session,
    user: User,
    tool_id_or_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """统一执行内置工具和自定义工具。"""

    ensure_tool_tables(db)
    if tool_id_or_name in BUILTIN_TOOLS:
        tool = BUILTIN_TOOLS[tool_id_or_name]
        validate_tool_arguments(
            tool.input_schema,
            arguments,
            tool_name=tool_id_or_name,
        )
        permission_warnings = check_user_tool_permissions(
            user,
            tool.permissions,
            strict=False,
        )
        return {
            "tool": tool.to_dict(),
            "result": invoke_builtin_tool(db, user, tool_id_or_name, arguments),
            **({"permission_warnings": permission_warnings} if permission_warnings else {}),
        }

    tool = get_custom_tool(db, user, tool_id_or_name)
    validate_tool_arguments(
        tool.input_schema,
        arguments,
        tool_name=tool.name,
    )
    permission_warnings = check_user_tool_permissions(
        user,
        tool.permissions or [],
        strict=False,
    )
    result = invoke_custom_tool(db, user, tool, arguments)
    if permission_warnings:
        result["permission_warnings"] = permission_warnings
    return result


__all__ = ["get_custom_tool", "invoke_builtin_tool", "invoke_tool"]
