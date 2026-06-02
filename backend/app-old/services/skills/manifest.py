from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.errors import ValidationAppError


SUPPORTED_SKILL_RUNTIMES = {"prompt_skill", "agent_skill"}
DEFAULT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string"},
        "input": {"type": "string"},
    },
    "additionalProperties": True,
}
DEFAULT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output": {"type": "string"},
    },
    "additionalProperties": True,
}


def normalize_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    """标准化 Skill manifest，保证运行层看到稳定结构。"""

    manifest = deepcopy(raw or {})
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict):
        dependencies = {}
    manifest["dependencies"] = {
        "tools": _string_list(dependencies.get("tools")),
        "mcp_servers": _string_list(dependencies.get("mcp_servers")),
        "skills": _string_list(dependencies.get("skills")),
    }
    manifest["permissions"] = _string_list(manifest.get("permissions"))
    manifest["tests"] = [item for item in (manifest.get("tests") or []) if isinstance(item, dict)]
    manifest["runtime"] = str(manifest.get("runtime") or "prompt_skill")
    manifest["version"] = str(manifest.get("version") or "1.0.0")
    manifest["description"] = str(manifest.get("description") or "")
    manifest["entry"] = _normalize_entry(manifest.get("entry"))
    manifest["input_schema"] = _schema_or_default(manifest.get("input_schema"), DEFAULT_INPUT_SCHEMA)
    manifest["output_schema"] = _schema_or_default(manifest.get("output_schema"), DEFAULT_OUTPUT_SCHEMA)
    manifest["metadata"] = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
    return manifest


def validate_manifest(raw: dict[str, Any]) -> dict[str, Any]:
    manifest = normalize_manifest(raw)
    name = str(manifest.get("name") or "").strip()
    if not name:
        raise ValidationAppError("Skill manifest 缺少 name")
    if manifest["runtime"] not in SUPPORTED_SKILL_RUNTIMES:
        raise ValidationAppError(f"不支持的 Skill runtime: {manifest['runtime']}")
    _validate_schema(manifest["input_schema"], "input_schema")
    _validate_schema(manifest["output_schema"], "output_schema")
    manifest["name"] = name[:160]
    return manifest


def _normalize_entry(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"prompt": value}
    if isinstance(value, dict):
        return value
    return {"prompt": ""}


def _schema_or_default(value: Any, default: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) and value else deepcopy(default)


def _validate_schema(schema: dict[str, Any], field: str) -> None:
    schema_type = schema.get("type")
    if schema_type and schema_type not in {"object", "string", "number", "integer", "boolean", "array"}:
        raise ValidationAppError(f"Skill manifest {field} type 无效")
    if schema_type == "object" and "properties" in schema and not isinstance(schema["properties"], dict):
        raise ValidationAppError(f"Skill manifest {field}.properties 必须是 object")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
