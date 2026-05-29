from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MentionTargetFilter:
    agent_ids: set[str]
    agent_names: list[str]


def resolve_mention_target_filter(
    prompt: str,
    agents: list[Any],
) -> MentionTargetFilter | None:
    """解析本轮用户消息中的显式 @Agent 目标。

    只识别完整的 ``@Agent Name``，不做模糊匹配；这样未命中或不明确时，
    群聊仍保持原工作流行为。
    """
    text = prompt or ""
    if "@" not in text:
        return None

    name_to_agents: dict[str, list[Any]] = {}
    for agent in agents:
        name = str(getattr(agent, "name", "") or "").strip()
        agent_id = str(getattr(agent, "id", "") or "").strip()
        if name and agent_id:
            name_to_agents.setdefault(name.lower(), []).append(agent)

    occupied_ranges: list[tuple[int, int]] = []
    matched: list[tuple[str, str]] = []
    for name in sorted(
        {str(getattr(agent, "name", "") or "").strip() for agent in agents},
        key=len,
        reverse=True,
    ):
        if not name:
            continue
        owners = name_to_agents.get(name.lower(), [])
        if len(owners) != 1:
            continue
        marker = f"@{name}"
        start = 0
        while True:
            index = text.lower().find(marker.lower(), start)
            if index < 0:
                break
            end = index + len(marker)
            start = end
            if _overlaps(index, end, occupied_ranges) or not _has_name_boundary(text, end):
                continue
            occupied_ranges.append((index, end))
            agent = owners[0]
            matched.append((str(getattr(agent, "id")), str(getattr(agent, "name"))))
            break

    if not matched:
        return None
    agent_ids = {agent_id for agent_id, _ in matched}
    if not agent_ids:
        return None
    return MentionTargetFilter(
        agent_ids=agent_ids,
        agent_names=[name for agent_id, name in matched if agent_id in agent_ids],
    )


def _overlaps(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < existing_end and end > existing_start for existing_start, existing_end in ranges)


def _has_name_boundary(text: str, end: int) -> bool:
    if end >= len(text):
        return True
    next_char = text[end]
    if next_char.isspace():
        return True
    if next_char in "，。,.!?！？;；:：、)]）】》":
        return True
    return not next_char.isascii() or not (next_char.isalnum() or next_char in {"_", "-"})
