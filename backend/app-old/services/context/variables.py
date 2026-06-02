from __future__ import annotations

import json
import re
from typing import Any


REFERENCE_PATTERN = re.compile(r"\{\{\s*(?P<expr>[A-Za-z0-9_.:-]+)\s*\}\}")


def resolve_value(value: Any, scope: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_value(item, scope) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, scope) for item in value]
    if not isinstance(value, str):
        return value
    matched = REFERENCE_PATTERN.fullmatch(value.strip())
    if matched:
        return lookup(scope, matched.group("expr"))
    return REFERENCE_PATTERN.sub(lambda item: stringify(lookup(scope, item.group("expr"))), value)


def lookup(scope: dict[str, Any], expr: str) -> Any:
    current: Any = scope
    for part in expr.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
        if current is None:
            return ""
    return current


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str, indent=2)
    return str(value)


def artifact_reference_scope(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    by_key: dict[str, Any] = {}
    for artifact in artifacts:
        artifact_id = str(artifact.get("id") or artifact.get("artifact_id") or "")
        title = str(artifact.get("title") or artifact.get("name") or "")
        if artifact_id:
            by_key[artifact_id] = artifact
        if title:
            by_key[title] = artifact
    return by_key
