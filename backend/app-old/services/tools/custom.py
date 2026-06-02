from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.models import ToolDefinition, User, utcnow
from app.services.serialization import tool_definition_to_dict


def _run_custom_python(tool: ToolDefinition, arguments: dict[str, Any]) -> dict[str, Any]:
    code = str((tool.implementation or {}).get("code") or "").strip()
    if not code:
        return {"status": "noop", "result": arguments, "message": "工具暂无代码，已返回输入参数。"}
    if re.search(r"\b(import|open|exec|eval|compile|__|os\.|subprocess|socket|shutil)\b", code):
        raise ValidationAppError("自定义工具代码包含未授权的高风险能力，请改用 sandbox.run 或 MCP 工具。")
    safe_builtins = {
        "len": len,
        "min": min,
        "max": max,
        "sum": sum,
        "sorted": sorted,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
        "list": list,
        "dict": dict,
        "enumerate": enumerate,
        "range": range,
    }
    namespace: dict[str, Any] = {"arguments": arguments, "result": None, "json": json}
    exec(code, {"__builtins__": safe_builtins}, namespace)
    return {"status": "succeeded", "result": namespace.get("result")}


def invoke_custom_tool(
    db: Session,
    user: User,
    tool: ToolDefinition,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool.status != "active":
        raise ValidationAppError("?????")
    result = _run_custom_python(tool, arguments)
    tool.extra = {
        **(tool.extra or {}),
        "last_invocation_at": utcnow().isoformat().replace("+00:00", "Z"),
    }
    db.flush()
    return {"tool": tool_definition_to_dict(tool), "result": result}
