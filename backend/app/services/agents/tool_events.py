from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import ToolInvocation

FAILED_STATUSES = {"failed", "error", "cancelled", "timeout"}


def tool_event_from_record(db: Session, record: dict[str, Any]) -> dict[str, Any]:
    """把一次 Function Call 执行记录压缩成可展示、可持久化的工具事件。"""
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    output = _output_value(result)
    invocation = _tool_invocation(db, result.get("invocation_id"))
    status = _status(record, result, invocation)
    event: dict[str, Any] = {
        "tool_name": str(record.get("tool_name") or result.get("tool_name") or ""),
        "tool_call_id": str(record.get("tool_call_id") or ""),
        "status": status,
    }
    if invocation:
        event["invocation_id"] = invocation.id
        event["duration_ms"] = invocation.duration_ms
        event["status"] = invocation.status or status
        if invocation.error_message:
            event["error"] = _short(invocation.error_message)
    _merge_output_fields(event, output)
    event["summary"] = _summary(event, output)
    return {key: value for key, value in event.items() if value not in (None, "")}


def _tool_invocation(db: Session, invocation_id: Any) -> ToolInvocation | None:
    if not invocation_id:
        return None
    try:
        return db.get(ToolInvocation, str(invocation_id))
    except Exception:
        return None


def _status(
    record: dict[str, Any],
    result: dict[str, Any],
    invocation: ToolInvocation | None,
) -> str:
    if invocation and invocation.status:
        return str(invocation.status)
    value = record.get("status") or result.get("status") or "unknown"
    return str(value)


def _output_value(result: dict[str, Any]) -> Any:
    if "output" in result:
        return result.get("output")
    if "result" in result:
        return result.get("result")
    return result


def _merge_output_fields(event: dict[str, Any], output: Any) -> None:
    if not isinstance(output, dict):
        if output:
            event["stdout"] = _short(output)
        return
    nested = output.get("result") if isinstance(output.get("result"), dict) else {}
    event["exit_code"] = _first(output, "exit_code", "return_code", "code") or _first(
        nested,
        "exit_code",
        "return_code",
        "code",
    )
    event["duration_ms"] = event.get("duration_ms") or _first(
        output,
        "duration_ms",
        "elapsed_ms",
    ) or _first(nested, "duration_ms", "elapsed_ms")
    event["stdout"] = _short(
        _first(output, "stdout", "stdout_tail", "output", "text")
        or _first(nested, "stdout", "stdout_tail", "output", "text")
    )
    event["stderr"] = _short(
        _first(output, "stderr", "stderr_tail") or _first(nested, "stderr", "stderr_tail")
    )
    event["error"] = _short(
        _first(output, "error", "error_message") or _first(nested, "error", "error_message")
    )


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _summary(event: dict[str, Any], output: Any) -> str:
    if str(event.get("status", "")).lower() in FAILED_STATUSES:
        return _short(event.get("error") or event.get("stderr") or output) or "工具调用失败"
    return _short(event.get("stdout") or output) or "工具调用完成"


def _short(value: Any, limit: int = 500) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else f"{text[:limit]}..."
