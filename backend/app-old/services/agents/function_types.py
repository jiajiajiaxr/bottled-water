from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import Message


@dataclass
class AgentFunctionLoopResult:
    assistant: Message | None
    text: str
    thinking: str
    tool_results: list[dict[str, Any]]
    tool_context: dict[str, Any]
