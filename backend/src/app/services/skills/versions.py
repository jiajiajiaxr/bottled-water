from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models import Skill, User, utcnow
from app.services.serialization import redact_sensitive
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.manifest import validate_manifest

_VERSIONED_FIELDS = (
    "name",
    "version",
    "runtime",
    "description",
    "entry",
    "input_schema",
    "output_schema",
    "dependencies",
    "permissions",
    "tests",
    "metadata",
)


def manifest_for_skill(skill: Skill) -> dict[str, Any]:
    return legacy_skill_manifest(skill)


def manifest_hash(manifest: dict[str, Any]) -> str:
    """生成稳定 manifest 指纹，用于版本审计和测试报告关联。"""

    normalized = validate_manifest(manifest)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def manifest_snapshot(manifest: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_manifest(manifest)
    return {
        "hash": manifest_hash(normalized),
        "manifest": redact_sensitive(normalized),
        "summary": {
            "name": normalized.get("name"),
            "version": normalized.get("version"),
            "runtime": normalized.get("runtime"),
            "description": normalized.get("description"),
            "dependencies": redact_sensitive(normalized.get("dependencies") or {}),
            "permissions": redact_sensitive(normalized.get("permissions") or []),
            "test_count": len(normalized.get("tests") or []),
        },
    }


def set_skill_manifest(skill: Skill, manifest: dict[str, Any], *, user: User | None = None) -> dict[str, Any]:
    normalized = validate_manifest(manifest)
    previous = legacy_skill_manifest(skill)
    metadata = dict(skill.extra or {})
    versions = metadata.get("versions") if isinstance(metadata.get("versions"), list) else []
    now = utcnow().isoformat().replace("+00:00", "Z")
    previous_hash = manifest_hash(previous)
    next_hash = manifest_hash(normalized)
    should_archive_previous = bool(skill.id) and previous_hash != next_hash
    if should_archive_previous:
        versions.append(
            {
                **manifest_snapshot(previous),
                "archived_at": now,
                "updated_by": user.id if user else None,
                "replaced_by": {
                    "version": normalized.get("version"),
                    "hash": next_hash,
                },
                "changed_fields": _changed_fields(previous, normalized),
            }
        )
    metadata["versions"] = versions[-20:]
    metadata["manifest"] = normalized
    metadata["manifest_hash"] = next_hash
    metadata["manifest_updated_at"] = now
    metadata["manifest_updated_by"] = user.id if user else None
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


def _changed_fields(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    return [field for field in _VERSIONED_FIELDS if previous.get(field) != current.get(field)]
