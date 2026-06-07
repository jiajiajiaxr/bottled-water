from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db.models import ConversationParticipant


def raw_agent_mentions(payload: dict[str, Any], content: dict[str, Any] | None = None) -> Any:
    if content and content.get("agent_mentions") is not None:
        return content.get("agent_mentions")
    return payload.get("agent_mentions")


def normalize_agent_mentions(
    db: Session,
    *,
    conversation_id: str,
    mentions: Any,
) -> list[dict[str, str]]:
    requested_ids = _requested_agent_ids(mentions)
    if not requested_ids:
        return []

    participants = db.scalars(
        select(ConversationParticipant)
        .options(selectinload(ConversationParticipant.agent))
        .where(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.participant_type == "agent",
            ConversationParticipant.left_at.is_(None),
            ConversationParticipant.agent_id.in_(requested_ids),
        )
    ).all()
    by_id = {
        str(participant.agent_id): participant
        for participant in participants
        if participant.agent_id
    }

    normalized: list[dict[str, str]] = []
    for agent_id in requested_ids:
        participant = by_id.get(agent_id)
        if not participant:
            continue
        agent = participant.agent
        name = str(getattr(agent, "name", "") or participant.nickname or agent_id).strip()
        normalized.append({"agent_id": agent_id, "agent_name": name})
    return normalized


def prepend_agent_mentions(text: str, mentions: list[dict[str, str]]) -> str:
    markers: list[str] = []
    lowered = (text or "").lower()
    for item in mentions:
        name = str(item.get("agent_name") or "").strip()
        if not name:
            continue
        marker = f"@{name}"
        if marker.lower() not in lowered:
            markers.append(marker)
    if not markers:
        return text
    return f"{' '.join(markers)} {text}".strip()


def _requested_agent_ids(mentions: Any) -> list[str]:
    if not isinstance(mentions, list):
        return []

    requested: list[str] = []
    for item in mentions:
        agent_id = ""
        if isinstance(item, dict):
            agent_id = str(item.get("agent_id") or item.get("id") or "").strip()
        elif isinstance(item, str):
            agent_id = item.strip()
        if agent_id and agent_id not in requested:
            requested.append(agent_id)
    return requested
