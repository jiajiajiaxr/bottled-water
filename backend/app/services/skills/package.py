from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Skill, User, utcnow
from app.services.serialization import redact_sensitive
from app.services.skills.catalog import ensure_skill_owner, ensure_skill_tables, validate_workspace
from app.services.skills.versions import set_skill_manifest


def install_skill_package(
    db: Session,
    user: User,
    manifest: dict[str, Any],
    *,
    workspace_id: str | None = None,
    source: str = "manual",
    category: str = "general",
    tags: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> Skill:
    ensure_skill_tables(db)
    validate_workspace(db, user, workspace_id)
    skill = Skill(
        owner_id=user.id,
        workspace_id=workspace_id,
        name=str(manifest.get("name") or "Skill"),
        description=str(manifest.get("description") or ""),
        category=category,
        source=source,
        status="active",
        version=str(manifest.get("version") or "1.0.0"),
        content=str(manifest.get("entry", {}).get("content") or ""),
        prompt=str(manifest.get("entry", {}).get("prompt") or ""),
        input_schema=manifest.get("input_schema") or {},
        output_schema=manifest.get("output_schema") or {},
        tools=[],
        tags=tags or [],
        config=redact_sensitive(config or {}),
    )
    set_skill_manifest(skill, manifest, user=user)
    db.add(skill)
    return skill


def soft_delete_skill_package(db: Session, skill: Skill, user: User) -> None:
    ensure_skill_owner(skill, user)
    skill.deleted_at = utcnow()
    skill.status = "deleted"
    db.flush()
