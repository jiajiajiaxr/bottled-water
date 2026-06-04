"""Conversation scheduling strategy helpers.

This module keeps strategy resolution close to the chat boundary so API,
WebSocket, and runtime session creation use the same rules.
"""

from __future__ import annotations

from typing import Any

SUPPORTED_SCHEDULING_STRATEGIES = {"workflow", "tech_lead"}
DEFAULT_SCHEDULING_STRATEGY = "tech_lead"


def normalize_scheduling_strategy(value: Any) -> str:
    strategy = str(value or "").strip()
    return strategy if strategy in SUPPORTED_SCHEDULING_STRATEGIES else ""


def conversation_has_workflow(conversation: Any) -> bool:
    extra = conversation.extra if isinstance(getattr(conversation, "extra", None), dict) else {}
    workflow = extra.get("workflow")
    return isinstance(workflow, dict) and bool(workflow.get("nodes"))


def resolve_scheduling_strategy(conversation: Any, requested: Any = None) -> str:
    """Resolve message/session scheduling with one canonical precedence order.

    Precedence:
    1. explicit message-level strategy
    2. persisted conversation strategy
    3. group conversations with a saved workflow default to workflow
    4. tech_lead fallback
    """

    explicit = normalize_scheduling_strategy(requested)
    if explicit:
        return explicit

    extra = conversation.extra if isinstance(getattr(conversation, "extra", None), dict) else {}
    persisted = normalize_scheduling_strategy(extra.get("scheduling_strategy"))
    if persisted:
        return persisted

    if getattr(conversation, "chat_type", "") == "group" and conversation_has_workflow(conversation):
        return "workflow"

    return DEFAULT_SCHEDULING_STRATEGY


def persist_scheduling_strategy(conversation: Any, strategy: str) -> bool:
    """Persist a valid strategy into conversation.extra.

    Returns True when the object was changed.
    """

    normalized = normalize_scheduling_strategy(strategy)
    if not normalized:
        return False

    extra = dict(conversation.extra or {})
    if extra.get("scheduling_strategy") == normalized:
        return False
    extra["scheduling_strategy"] = normalized
    conversation.extra = extra
    return True
