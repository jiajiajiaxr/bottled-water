from __future__ import annotations

import json
from typing import Any


CHARS_PER_TOKEN = 4
DEFAULT_CONTEXT_TOKENS = 12_000


def estimate_tokens(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return max(1, len(text) // CHARS_PER_TOKEN)


def trim_text(value: str, *, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    head = max_chars // 2
    tail = max_chars - head - 80
    return f"{value[:head]}\n...[context trimmed]...\n{value[-max(0, tail):]}"


def compact_json(value: Any, *, max_chars: int = 4000) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
    return trim_text(text, max_chars=max_chars)


def fit_sections(
    sections: list[tuple[str, str]],
    *,
    token_budget: int = DEFAULT_CONTEXT_TOKENS,
) -> list[tuple[str, str]]:
    budget_chars = max(1000, token_budget * CHARS_PER_TOKEN)
    used = 0
    fitted: list[tuple[str, str]] = []
    for title, body in sections:
        if not body:
            continue
        remaining = budget_chars - used
        if remaining <= 0:
            break
        clipped = trim_text(body, max_chars=min(len(body), remaining))
        fitted.append((title, clipped))
        used += len(clipped)
    return fitted


def join_sections(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"## {title}\n{body}" for title, body in sections if body)
