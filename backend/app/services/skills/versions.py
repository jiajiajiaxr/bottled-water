from __future__ import annotations

from typing import Any

from app.models import Skill, User, utcnow
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.manifest import validate_manifest


def manifest_for_skill(skill: Skill) -> dict[str, Any]:
    return legacy_skill_manifest(skill)


def set_skill_manifest(skill: Skill, manifest: dict[str, Any], *, user: User | None = None) -> dict[str, Any]:
    normalized = validate_manifest(manifest)
    previous = legacy_skill_manifest(skill)
    metadata = dict(skill.extra or {})
    versions = metadata.get("versions") if isinstance(metadata.get("versions"), list) else []
    versions.append(
        {
            "version": previous.get("version"),
            "name": previous.get("name"),
            "updated_at": utcnow().isoformat().replace("+00:00", "Z"),
            "updated_by": user.id if user else None,
        }
    )
    metadata["versions"] = versions[-20:]
    metadata["manifest"] = normalized
    skill.extra = metadata
    skill.name = normalized["name"]
    skill.description = normalized.get("description", "")
    skill.version = normalized.get("version", skill.version)
    skill.input_schema = normalized.get("input_schema") or {}
    skill.output_schema = normalized.get("output_schema") or {}
    return normalized


def skill_version_history(skill: Skill) -> list[dict[str, Any]]:
    metadata = skill.extra or {}
    versions = metadata.get("versions")
    return versions if isinstance(versions, list) else []
