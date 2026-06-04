from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationAppError
from app.models import McpServer, Skill, ToolDefinition, User
from app.services.tools.catalog import get_tool_definition, sync_builtin_tool_definitions


def check_skill_dependencies(
    db: Session,
    manifest: dict[str, Any],
    *,
    user: User | None = None,
) -> dict[str, Any]:
    deps = manifest.get("dependencies") if isinstance(manifest.get("dependencies"), dict) else {}
    tool_report = _tool_dependency_report(db, user, deps.get("tools") or [])
    mcp_report = _mcp_dependency_report(db, deps.get("mcp_servers") or [])
    skill_report = _skill_dependency_report(db, deps.get("skills") or [])
    missing = {
        "tools": [item["name"] for item in tool_report if not item["ok"]],
        "mcp_servers": [item["id"] for item in mcp_report if not item["ok"]],
        "skills": [item["id"] for item in skill_report if not item["ok"]],
    }
    return {
        "ok": not any(missing.values()),
        "missing": missing,
        "permissions": manifest.get("permissions") or [],
        "resolved": {
            "tools": tool_report,
            "mcp_servers": mcp_report,
            "skills": skill_report,
        },
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
    return [item["name"] for item in _tool_dependency_report(db, user, names) if not item["ok"]]


def _missing_mcp_servers(db: Session, ids: list[str]) -> list[str]:
    return [item["id"] for item in _mcp_dependency_report(db, ids) if not item["ok"]]


def _missing_skills(db: Session, ids: list[str]) -> list[str]:
    return [item["id"] for item in _skill_dependency_report(db, ids) if not item["ok"]]


def _tool_dependency_report(db: Session, user: User | None, names: list[str]) -> list[dict[str, Any]]:
    if not names:
        return []
    sync_builtin_tool_definitions(db)
    report: list[dict[str, Any]] = []
    for name in names:
        if not user:
            tool = db.scalar(
                select(ToolDefinition).where(
                    ToolDefinition.owner_id.is_(None),
                    ToolDefinition.workspace_id.is_(None),
                    ToolDefinition.name == name,
                    ToolDefinition.deleted_at.is_(None),
                    ToolDefinition.status == "active",
                )
            )
            if tool:
                report.append(
                    {
                        "name": name,
                        "ok": True,
                        "tool_id": tool.id,
                        "type": tool.type,
                        "is_builtin": bool(tool.is_builtin),
                        "workspace_id": tool.workspace_id,
                    }
                )
            else:
                report.append({"name": name, "ok": False, "reason": "user_required"})
            continue
        try:
            tool = get_tool_definition(db, user, name)
        except Exception:
            report.append({"name": name, "ok": False, "reason": "not_found_or_not_visible"})
            continue
        if tool.status != "active" or tool.deleted_at is not None:
            report.append({"name": name, "ok": False, "reason": "inactive_or_deleted"})
            continue
        report.append(
            {
                "name": name,
                "ok": True,
                "tool_id": tool.id,
                "type": tool.type,
                "is_builtin": bool(tool.is_builtin),
                "workspace_id": tool.workspace_id,
            }
        )
    return report


def _mcp_dependency_report(db: Session, ids: list[str]) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for server_id in ids:
        server = db.get(McpServer, server_id)
        if not server or server.deleted_at is not None:
            report.append({"id": server_id, "ok": False, "reason": "not_found_or_deleted"})
            continue
        if not server.enabled:
            report.append({"id": server_id, "ok": False, "reason": "disabled"})
            continue
        report.append(
            {
                "id": server_id,
                "ok": True,
                "name": server.name,
                "transport": server.transport,
                "health_status": server.health_status,
                "tool_count": len(server.tools or []),
            }
        )
    return report


def _skill_dependency_report(db: Session, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    found = {
        item.id: item
        for item in db.scalars(
            select(Skill).where(Skill.id.in_(ids), Skill.deleted_at.is_(None), Skill.status == "active")
        )
    }
    report: list[dict[str, Any]] = []
    for skill_id in ids:
        skill = found.get(skill_id)
        if not skill:
            report.append({"id": skill_id, "ok": False, "reason": "not_found_or_inactive"})
            continue
        report.append(
            {
                "id": skill_id,
                "ok": True,
                "name": skill.name,
                "version": skill.version,
                "runtime": (skill.extra or {}).get("manifest", {}).get("runtime")
                if isinstance(skill.extra, dict)
                else None,
            }
        )
    return report


def _ensure_permissions(manifest: dict[str, Any], user: User | None) -> None:
    permissions = set(manifest.get("permissions") or [])
    if "admin" in permissions and (not user or user.role != "admin"):
        raise ForbiddenError("Skill requires admin permission")
