from __future__ import annotations

from typing import Any

from app.core.errors import ValidationAppError


def validate_tool_arguments(
    schema: dict[str, Any] | None,
    arguments: dict[str, Any],
    *,
    tool_name: str,
) -> None:
    """按工具 JSON Schema 做轻量参数校验。"""

    if not schema:
        return
    _validate_object_schema(schema, arguments, path=tool_name)


def _validate_object_schema(schema: dict[str, Any], value: Any, *, path: str) -> None:
    expected_type = schema.get("type")
    if expected_type and expected_type != "object":
        _validate_type(expected_type, value, path=path)
        return
    if not isinstance(value, dict):
        raise ValidationAppError(f"{path} 参数必须是 object")

    required = schema.get("required") if isinstance(schema.get("required"), list) else []
    for key in required:
        if key not in value or value[key] in (None, ""):
            raise ValidationAppError(f"{path}.{key} 是必填参数")

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return
    for key, child_schema in properties.items():
        if key not in value or not isinstance(child_schema, dict):
            continue
        child_path = f"{path}.{key}"
        child_type = child_schema.get("type")
        if child_type == "object" and isinstance(value[key], dict):
            _validate_object_schema(child_schema, value[key], path=child_path)
        elif child_type:
            _validate_type(child_type, value[key], path=child_path)


def _validate_type(expected: str | list[str], value: Any, *, path: str) -> None:
    expected_types = expected if isinstance(expected, list) else [expected]
    if "null" in expected_types and value is None:
        return
    validators = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    if not any(validators.get(item, lambda _value: True)(value) for item in expected_types):
        expected_text = " | ".join(expected_types)
        raise ValidationAppError(f"{path} 类型错误，应为 {expected_text}")
