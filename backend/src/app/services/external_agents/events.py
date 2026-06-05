from __future__ import annotations

import re
from typing import Any


SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*([^\s'\"]+)"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=]{12,}"),
    re.compile(r"(?i)(sk-[A-Za-z0-9]{8,})"),
)


def redact_secrets(text: str) -> str:
    value = text or ""
    for pattern in SECRET_PATTERNS:
        if pattern.groups >= 2:
            value = pattern.sub(lambda m: f"{m.group(1)}=<redacted>", value)
        else:
            value = pattern.sub("<redacted>", value)
    return value


def tail_text(lines: list[str], *, limit: int = 8000) -> str:
    value = "\n".join(lines)
    if len(value) <= limit:
        return value
    return value[-limit:]


def external_agent_event(
    event_type: str,
    *,
    provider: str,
    run_id: str,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "provider": provider,
        "run_id": run_id,
        "message": redact_secrets(message),
        "data": data or {},
    }


def summarize_events(events: list[dict[str, Any]], *, limit: int = 40) -> list[dict[str, Any]]:
    if len(events) <= limit:
        return events
    return [*events[:5], {"type": "truncated", "message": f"省略 {len(events) - limit} 条事件"}, *events[-(limit - 6):]]
