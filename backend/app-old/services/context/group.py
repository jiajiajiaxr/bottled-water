from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Conversation, ConversationParticipant, McpServer, Skill
from app.services.context.compression import trim_text
from app.services.tools.builtins.registry import BUILTIN_TOOLS
from app.services.tools.permissions import normalize_tool_names


@dataclass
class SpeakerIdentity:
    sender_type: str
    name: str
    role: str = ""
    sender_id: str = ""

    def prefix(self) -> str:
        if self.sender_type == "agent":
            role = self.role or "agent"
            return f"[Agent: {self.name} | role={role} | id={self.sender_id}]"
        return f"[User: {self.name}]"


@dataclass
class GroupMemberContext:
    text: str = ""
    speaker_identities: dict[str, SpeakerIdentity] = field(default_factory=dict)


def build_group_member_context(
    db: Session,
    conversation: Conversation,
    current_agent: Agent,
) -> GroupMemberContext:
    if conversation.chat_type != "group":
        return GroupMemberContext()
    participants = db.scalars(
        select(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation.id,
            ConversationParticipant.left_at.is_(None),
        )
        .order_by(ConversationParticipant.joined_at.asc())
    ).all()
    agent_ids = [item.agent_id for item in participants if item.participant_type == "agent" and item.agent_id]
    agents = {
        item.id: item
        for item in db.scalars(select(Agent).where(Agent.id.in_(agent_ids))).all()
    } if agent_ids else {}
    skill_names = _skill_names(db, agents.values())
    mcp_names = _mcp_names(db, agents.values())
    identities: dict[str, SpeakerIdentity] = {}
    lines = [
        f"你是当前 Agent：{current_agent.name}（role={current_agent.type}, id={current_agent.id}）。",
        "其他群聊成员是协作者；你可以引用他们的发言和分工，但不要冒充他们发言。",
        "群聊成员清单：",
    ]
    for participant in participants:
        if participant.participant_type == "agent" and participant.agent_id:
            agent = agents.get(participant.agent_id)
            if not agent:
                continue
            identities[agent.id] = SpeakerIdentity(
                sender_type="agent",
                name=participant.nickname or agent.name,
                role=agent.type,
                sender_id=agent.id,
            )
            marker = "（当前 Agent）" if agent.id == current_agent.id else ""
            lines.append(
                "- "
                f"{participant.nickname or agent.name}{marker}: "
                f"role={agent.type}; "
                f"description={trim_text(agent.description or '', max_chars=180)}; "
                f"tools={', '.join(_tool_summary(agent)) or '无'}; "
                f"skills={', '.join(skill_names.get(agent.id, [])) or '无'}; "
                f"mcp={', '.join(mcp_names.get(agent.id, [])) or '无'}"
            )
        elif participant.participant_type == "user" and participant.user_id:
            name = participant.nickname or "用户"
            identities[participant.user_id] = SpeakerIdentity(
                sender_type="user",
                name=name,
                sender_id=participant.user_id,
            )
            lines.append(f"- {name}: role=user; description=群聊用户")
    return GroupMemberContext(
        text=trim_text("\n".join(lines), max_chars=6000),
        speaker_identities=identities,
    )


def format_group_message_content(
    *,
    sender_type: str,
    sender_id: str | None,
    sender_name: str,
    text: str,
    identities: dict[str, SpeakerIdentity],
) -> str:
    identity = identities.get(str(sender_id or ""))
    if not identity:
        if sender_type == "agent":
            identity = SpeakerIdentity(
                sender_type="agent",
                name=sender_name or "Agent",
                role="agent",
                sender_id=str(sender_id or ""),
            )
        else:
            identity = SpeakerIdentity(
                sender_type="user",
                name=sender_name or "用户",
                sender_id=str(sender_id or ""),
            )
    return f"{identity.prefix()}\n{text}"


def _tool_summary(agent: Agent) -> list[str]:
    names = normalize_tool_names((agent.config or {}).get("tools") or [])
    output: list[str] = []
    for name in names[:12]:
        builtin = BUILTIN_TOOLS.get(name)
        output.append(builtin.name if builtin else name)
    return output


def _skill_names(db: Session, agents: Any) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    wanted: set[str] = set()
    agent_list = list(agents)
    for agent in agent_list:
        ids = [str(item) for item in (agent.config or {}).get("skill_ids") or [] if item]
        mapping[agent.id] = ids
        wanted.update(ids)
    if not wanted:
        return mapping
    rows = db.scalars(select(Skill).where(Skill.id.in_(wanted), Skill.deleted_at.is_(None))).all()
    names = {item.id: item.name for item in rows}
    return {agent_id: [names.get(item, item) for item in ids] for agent_id, ids in mapping.items()}


def _mcp_names(db: Session, agents: Any) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    wanted: set[str] = set()
    agent_list = list(agents)
    for agent in agent_list:
        ids = [str(item) for item in (agent.config or {}).get("mcp_server_ids") or [] if item]
        mapping[agent.id] = ids
        wanted.update(ids)
    if not wanted:
        return mapping
    rows = db.scalars(select(McpServer).where(McpServer.id.in_(wanted), McpServer.deleted_at.is_(None))).all()
    names = {item.id: item.name for item in rows}
    return {agent_id: [names.get(item, item) for item in ids] for agent_id, ids in mapping.items()}
