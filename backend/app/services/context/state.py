from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Conversation, Message, utcnow
from app.services.context.compression import compact_json, trim_text


STATE_KEYS = ("last_math_result", "last_topic", "last_artifact_id", "pending_reference")


def conversation_state(conversation: Conversation) -> dict[str, Any]:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    context = extra.get("context") if isinstance(extra.get("context"), dict) else {}
    state = context.get("state") or extra.get("conversation_state") or {}
    return dict(state) if isinstance(state, dict) else {}


def conversation_variables(conversation: Conversation) -> dict[str, Any]:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    variables = extra.get("conversation_variables")
    return dict(variables) if isinstance(variables, dict) else {}


def conversation_state_text(conversation: Conversation) -> str:
    state = conversation_state(conversation)
    variables = conversation_variables(conversation)
    visible = {key: state.get(key) for key in STATE_KEYS if state.get(key) is not None}
    if variables:
        visible["conversation_variables"] = variables
    if not visible:
        return ""
    return compact_json(visible, max_chars=3000)


def update_conversation_state_after_turn(
    db: Session,
    conversation: Conversation,
    *,
    user_message: Message,
    assistant_message: Message | None,
    final_text: str,
    tool_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    user_text = _message_text(user_message)
    assistant_text = final_text or _message_text(assistant_message)
    previous = conversation_state(conversation)
    state = dict(previous)

    math_result = _extract_math_result(user_text, assistant_text)
    if math_result is not None:
        state["last_math_result"] = math_result

    topic = _extract_topic(user_text)
    if topic:
        state["last_topic"] = topic

    artifact_id = _extract_artifact_id(tool_results or [])
    if artifact_id:
        state["last_artifact_id"] = artifact_id
        state["pending_reference"] = {"type": "artifact", "id": artifact_id}
    elif topic:
        state["pending_reference"] = {"type": "topic", "text": topic}

    if not state:
        return {}
    state["updated_at"] = utcnow().isoformat()
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    context = extra.get("context") if isinstance(extra.get("context"), dict) else {}
    variables = extra.get("conversation_variables") if isinstance(extra.get("conversation_variables"), dict) else {}
    variables = _sync_variables(variables, state)
    conversation.extra = {
        **extra,
        "context": {**context, "state": state},
        "conversation_state": state,
        "conversation_variables": variables,
    }
    db.flush()
    return state


def _sync_variables(variables: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    synced = dict(variables)
    for key in STATE_KEYS:
        if key in state:
            synced[key] = state[key]
    return synced


def _extract_math_result(user_text: str, assistant_text: str) -> int | float | None:
    if not re.search(r"(\d|加|减|乘|除|等于|算|多少|几)", user_text + assistant_text):
        return None
    candidates = re.findall(r"-?\d+(?:\.\d+)?", assistant_text)
    if not candidates:
        return None
    raw = candidates[-1]
    value = float(raw) if "." in raw else int(raw)
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _extract_topic(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return ""
    if re.fullmatch(r"[\d\s+\-*/÷×=＝？?呢几多少加减乘除]+", clean):
        return ""
    return trim_text(clean, max_chars=120)


def _extract_artifact_id(tool_results: list[dict[str, Any]]) -> str:
    for item in reversed(tool_results):
        found = _find_key(item.get("result"), "artifact_id") or _find_key(item, "artifact_id")
        if found:
            return str(found)
    return ""


def _find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if value.get(key):
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found:
                return found
    return None


def _message_text(message: Message | None) -> str:
    if not message:
        return ""
    return str((message.content or {}).get("text") or "").strip()
