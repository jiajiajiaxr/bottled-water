from __future__ import annotations

import hashlib
import secrets
from typing import Any

from app.models import Conversation


def generate_group_number() -> str:
    """Return a user-facing 12-digit group number for newly created groups."""
    return "".join(secrets.choice("0123456789") for _ in range(12))


def fallback_group_number(conversation_id: str) -> str:
    """Stable fallback for legacy group conversations without a stored number."""
    digest = hashlib.sha256(str(conversation_id).encode("utf-8")).hexdigest()
    return f"{int(digest[:16], 16) % 1_000_000_000_000:012d}"


def conversation_group_number(conversation: Conversation) -> str | None:
    if conversation.chat_type != "group":
        return None
    extra: dict[str, Any] = conversation.extra if isinstance(conversation.extra, dict) else {}
    stored = str(extra.get("group_number") or "").strip()
    if stored and stored.isdigit() and len(stored) == 12:
        return stored
    return fallback_group_number(conversation.id)
