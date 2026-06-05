from __future__ import annotations

from typing import Any

from app.models import Skill
from app.services.skills.manifest import validate_manifest


def legacy_skill_manifest(skill: Skill) -> dict[str, Any]:
    """把旧 skills 表记录转换成新的 Skill package manifest。"""

    metadata = skill.extra if isinstance(skill.extra, dict) else {}
    manifest = metadata.get("manifest") if isinstance(metadata.get("manifest"), dict) else None
    if manifest:
        return validate_manifest(_merge_legacy_defaults(skill, manifest))
    return validate_manifest(_legacy_default_manifest(skill))


def _merge_legacy_defaults(skill: Skill, manifest: dict[str, Any]) -> dict[str, Any]:
    merged = {
        **_legacy_default_manifest(skill),
        **manifest,
        "dependencies": {
            **_legacy_default_manifest(skill).get("dependencies", {}),
            **(manifest.get("dependencies") if isinstance(manifest.get("dependencies"), dict) else {}),
        },
        "metadata": {
            **_legacy_default_manifest(skill).get("metadata", {}),
            **(manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}),
        },
    }
    return merged


def _legacy_default_manifest(skill: Skill) -> dict[str, Any]:
    tool_refs = [item for item in _list(skill.tools) if isinstance(item, dict)]
    mcp_refs = [
        item
        for item in tool_refs
        if item.get("type") == "mcp" and item.get("server_id") and item.get("name")
    ]
    tool_names = [
        str(item.get("name") or item.get("tool_name"))
        for item in tool_refs
        if item.get("type") != "mcp" and (item.get("name") or item.get("tool_name"))
    ]
    mcp_server_ids = list(dict.fromkeys(str(item["server_id"]) for item in mcp_refs))
    config = skill.config if isinstance(skill.config, dict) else {}
    return {
        "name": _text(skill.name, "Skill"),
        "version": _text(skill.version, "1.0.0"),
        "description": _text(skill.description, ""),
        "runtime": str(config.get("runtime") or "prompt_skill"),
        "entry": {
            "prompt": _text(
                skill.prompt or skill.content,
                f"You are the AgentHub skill {_text(skill.name, 'Skill')}.",
            ),
            "content": _text(skill.content, ""),
            "legacy_tool_refs": tool_refs,
        },
        "input_schema": skill.input_schema if isinstance(skill.input_schema, dict) else {},
        "output_schema": skill.output_schema if isinstance(skill.output_schema, dict) else {},
        "dependencies": {
            "tools": list(dict.fromkeys(tool_names)),
            "mcp_servers": mcp_server_ids,
            "skills": [
                str(item) for item in config.get("skill_dependencies", []) if item
            ]
            if isinstance(config.get("skill_dependencies"), list)
            else [],
        },
        "permissions": [
            str(item) for item in config.get("permissions", []) if item
        ]
        if isinstance(config.get("permissions"), list)
        else [],
        "tests": config.get("tests") if isinstance(config.get("tests"), list) else [],
        "metadata": {
            "legacy": True,
            "source": _text(skill.source, ""),
            "category": _text(skill.category, "general"),
            "tags": _list(skill.tags),
        },
    }


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, fallback: str) -> str:
    return str(value) if isinstance(value, str) and value else fallback
