from __future__ import annotations

from typing import Any

from app.models import User
from app.services.audit import has_permission
from app.services.tools.builtins import BUILTIN_TOOLS


def normalize_tool_names(values: list[Any]) -> list[str]:
    """规范化 Agent 配置中的工具名称。"""

    names = []
    aliases = {
        "file_read": "file.read",
        "file_write": "file.write",
        "code_execute": "sandbox.run",
        "sandbox_run": "sandbox.run",
        "knowledge_retrieve": "file.summarize",
        "deploy": "deploy.preview",
        "mcp": "mcp.invoke",
        "skills": "skill.run",
    }
    for item in values:
        name = str(item.get("name") if isinstance(item, dict) else item).strip()
        if not name:
            continue
        names.append(aliases.get(name, name))
    return list(dict.fromkeys(names))


def allowed_builtin_tools(values: list[Any]) -> list[str]:
    """规范化工具名，并只保留已注册的内置工具。"""

    return [name for name in normalize_tool_names(values) if name in BUILTIN_TOOLS]


def check_user_tool_permissions(
    user: User,
    required_permissions: list[str] | tuple[str, ...],
    *,
    strict: bool = False,
) -> list[str]:
    """返回当前用户缺失的工具权限；默认不改变旧行为。"""

    missing = [
        permission
        for permission in required_permissions
        if permission and not has_permission(user, permission)
    ]
    if strict and missing:
        from app.core.errors import ForbiddenError

        raise ForbiddenError(f"缺少工具权限：{', '.join(missing)}")
    return missing
