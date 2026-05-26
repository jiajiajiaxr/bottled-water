from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services.tools.builtin_executor import invoke_builtin_tool
from app.services.tools.builtins import BUILTIN_TOOLS
from app.services.tools.catalog import ensure_tool_tables, get_custom_tool
from app.services.tools.custom import invoke_custom_tool
from app.services.tools.permissions import check_user_tool_permissions
from app.services.tools.runs import finish_tool_invocation, start_tool_invocation
from app.services.tools.schema import validate_tool_arguments


def invoke_tool(
    db: Session,
    user: User,
    tool_id_or_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """统一执行内置工具和自定义工具。"""

    ensure_tool_tables(db)
    conversation_id = str(arguments.get("conversation_id") or "") or None
    if tool_id_or_name in BUILTIN_TOOLS:
        tool = BUILTIN_TOOLS[tool_id_or_name]
        invocation, started = start_tool_invocation(
            db,
            user=user,
            tool_name=tool_id_or_name,
            tool_type="builtin",
            arguments=arguments,
            conversation_id=conversation_id,
        )
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
        try:
            result = invoke_builtin_tool(db, user, tool_id_or_name, arguments)
            finish_tool_invocation(invocation, started, status=result.get("status", "succeeded"), result=result)
            return {
                "tool": tool.to_dict(),
                "result": result,
                "invocation_id": invocation.id,
                **({"permission_warnings": permission_warnings} if permission_warnings else {}),
            }
        except Exception as exc:
            finish_tool_invocation(invocation, started, status="failed", error=str(exc), result={"error": str(exc)})
            raise

    tool = get_custom_tool(db, user, tool_id_or_name)
    invocation, started = start_tool_invocation(
        db,
        user=user,
        tool_name=tool.name,
        tool_type=tool.type,
        arguments=arguments,
        tool=tool,
        conversation_id=conversation_id,
    )
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
    try:
        result = invoke_custom_tool(db, user, tool, arguments)
        status = result.get("result", {}).get("status") or result.get("status") or "succeeded"
        finish_tool_invocation(invocation, started, status=status, result=result)
    except Exception as exc:
        finish_tool_invocation(invocation, started, status="failed", error=str(exc), result={"error": str(exc)})
        raise
    result["invocation_id"] = invocation.id
    if permission_warnings:
        result["permission_warnings"] = permission_warnings
    return result


__all__ = ["get_custom_tool", "invoke_builtin_tool", "invoke_tool"]
