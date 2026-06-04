from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import Agent, Conversation
from app.services.context.compression import compact_json, trim_text


BLACKBOARD_HISTORY_LIMIT = 8
AGENT_CONTEXT_FRAME_LIMIT = 12


@dataclass(frozen=True)
class RuntimeContextView:
    blackboard_text: str
    agent_context_text: str
    blackboard: dict[str, Any]
    agent_context: dict[str, Any]

    def to_sections(self) -> list[tuple[str, str]]:
        return [
            ("Blackboard 全局共享上下文", self.blackboard_text),
            ("当前 Agent 私有上下文（Agent Context）", self.agent_context_text),
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "blackboard": self.blackboard,
            "agent_context": self.agent_context,
        }


def build_runtime_context_view(conversation: Conversation, agent: Agent) -> RuntimeContextView:
    """Build the documented Blackboard + Agent Context view for ContextBuilder.

    The runtime persistence layer stores shared state in ``conversation.extra.blackboard``
    and private per-agent frames in ``conversation.extra.agent_contexts``. ContextBuilder
    consumes those structures here instead of maintaining a parallel memory model.
    """

    extra = _dict(conversation.extra)
    blackboard = _dict(extra.get("blackboard"))
    agent_frames = _agent_frames(extra, str(agent.id))
    return RuntimeContextView(
        blackboard_text=_format_blackboard(blackboard),
        agent_context_text=_format_agent_context(agent_frames),
        blackboard={
            "present": bool(blackboard),
            "version": _safe_int(blackboard.get("version")),
            "summary_count": len(_list(blackboard.get("structured_summaries"))),
            "raw_history_count": len(_list(blackboard.get("raw_history"))),
            "kv_keys": sorted(str(key) for key in _dict(blackboard.get("kv_state")).keys()),
        },
        agent_context={
            "present": bool(agent_frames),
            "agent_id": str(agent.id),
            "frame_count": len(agent_frames),
        },
    )


def _format_blackboard(blackboard: dict[str, Any]) -> str:
    if not blackboard:
        return ""
    parts: list[str] = []
    version = _safe_int(blackboard.get("version"))
    if version:
        parts.append(f"版本：{version}")
    summaries = _list(blackboard.get("structured_summaries"))
    if summaries:
        lines = ["结构化摘要："]
        for item in summaries[-3:]:
            if isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or "摘要")
                body = str(item.get("content") or item.get("summary") or item.get("text") or "")
                lines.append(f"- {title}: {trim_text(body, max_chars=500)}")
            else:
                lines.append(f"- {trim_text(str(item), max_chars=500)}")
        parts.append("\n".join(lines))
    kv_state = _dict(blackboard.get("kv_state"))
    if kv_state:
        parts.append("共享状态变量：\n" + compact_json(kv_state, max_chars=3000))
    history = _list(blackboard.get("recent_history") or blackboard.get("raw_history"))
    if history:
        lines = ["近期共享历史："]
        for entry in history[-BLACKBOARD_HISTORY_LIMIT:]:
            lines.append(f"- {_format_history_entry(entry)}")
        parts.append("\n".join(lines))
    return trim_text("\n\n".join(parts), max_chars=9000)


def _format_agent_context(frames: list[dict[str, Any]]) -> str:
    if not frames:
        return ""
    lines = [
        "以下内容只属于当前 Agent 的私有上下文，用于恢复该 Agent 自己的任务、思考和工具结果；不要泄露或假装来自其他 Agent。"
    ]
    for frame in frames[-AGENT_CONTEXT_FRAME_LIMIT:]:
        frame_type = str(frame.get("type") or frame.get("frame_type") or "context")
        content = frame.get("content", "")
        timestamp = frame.get("timestamp")
        prefix = f"- [{frame_type}]"
        if timestamp:
            prefix += f" {timestamp}"
        lines.append(f"{prefix}: {_stringify_content(content, max_chars=700)}")
    return trim_text("\n".join(lines), max_chars=9000)


def _format_history_entry(entry: Any) -> str:
    if not isinstance(entry, dict):
        return trim_text(str(entry), max_chars=700)
    entry_type = str(entry.get("type") or entry.get("event") or "event")
    actor = entry.get("agent_id") or entry.get("sender") or entry.get("sender_id") or ""
    content = (
        entry.get("content")
        if "content" in entry
        else entry.get("output", entry.get("text", entry.get("summary", "")))
    )
    actor_part = f" agent={actor}" if actor else ""
    return f"[{entry_type}{actor_part}] {_stringify_content(content, max_chars=700)}"


def _agent_frames(extra: dict[str, Any], agent_id: str) -> list[dict[str, Any]]:
    contexts = _dict(extra.get("agent_contexts") or extra.get("agent_context"))
    candidates = [
        agent_id,
        str(agent_id),
    ]
    for key in candidates:
        frames = contexts.get(key)
        if isinstance(frames, list):
            return [item for item in frames if isinstance(item, dict)]
        if isinstance(frames, dict):
            nested = frames.get("frames")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _stringify_content(value: Any, *, max_chars: int) -> str:
    if isinstance(value, str):
        return trim_text(value, max_chars=max_chars)
    return compact_json(value, max_chars=max_chars)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
