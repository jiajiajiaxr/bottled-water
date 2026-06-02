from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationAppError
from app.models import McpServer, Skill, User
from app.services.tools.builtins.registry import BUILTIN_TOOLS
from app.services.tools.catalog import get_custom_tool


def check_skill_dependencies(
    db: Session,
    manifest: dict[str, Any],
    *,
    user: User | None = None,
) -> dict[str, Any]:
    deps = manifest.get("dependencies") if isinstance(manifest.get("dependencies"), dict) else {}
    missing = {
        "tools": _missing_tools(db, user, deps.get("tools") or []),
        "mcp_servers": _missing_mcp_servers(db, deps.get("mcp_servers") or []),
        "skills": _missing_skills(db, deps.get("skills") or []),
    }
    return {
        "ok": not any(missing.values()),
        "missing": missing,
        "permissions": manifest.get("permissions") or [],
    }


def ensure_skill_dependencies(
    db: Session,
    manifest: dict[str, Any],
    *,
    user: User | None = None,
) -> dict[str, Any]:
    report = check_skill_dependencies(db, manifest, user=user)
    if not report["ok"]:
        raise ValidationAppError(f"Skill 依赖缺失: {report['missing']}")
    _ensure_permissions(manifest, user)
    return report


def _missing_tools(db: Session, user: User | None, names: list[str]) -> list[str]:
    missing: list[str] = []
    for name in names:
        if name in BUILTIN_TOOLS:
            continue
        if not user:
            missing.append(name)
            continue
        try:
            get_custom_tool(db, user, name)
        except Exception:
            missing.append(name)
    return missing


def _missing_mcp_servers(db: Session, ids: list[str]) -> list[str]:
    missing: list[str] = []
    for server_id in ids:
        server = db.get(McpServer, server_id)
        if not server or server.deleted_at is not None or not server.enabled:
            missing.append(server_id)
    return missing


def _missing_skills(db: Session, ids: list[str]) -> list[str]:
    if not ids:
        return []
    found = {
        item.id
        for item in db.scalars(
            select(Skill).where(Skill.id.in_(ids), Skill.deleted_at.is_(None), Skill.status == "active")
        )
    }
    return [item for item in ids if item not in found]


def _ensure_permissions(manifest: dict[str, Any], user: User | None) -> None:
    permissions = set(manifest.get("permissions") or [])
    if "admin" in permissions and (not user or user.role != "admin"):
        raise ForbiddenError("Skill requires admin permission")
