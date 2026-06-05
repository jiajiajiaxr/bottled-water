from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, McpServer, Skill, ToolDefinition, utcnow


TEST_MCP_PREFIXES = ("Acceptance ",)
TEST_TOOL_PREFIXES = ("custom_echo_acceptance",)
TEST_SKILL_NAMES = {"Release Notes Skill", "Filesystem Read Skill"}
TEST_AGENT_PATTERNS = ("acceptance config agent", "acceptance agent")


def cleanup_acceptance_residue(db: Session) -> None:
    """Soft-delete acceptance residue that leaked into demo catalogs."""

    now = utcnow()
    for server in db.scalars(select(McpServer).where(McpServer.deleted_at.is_(None))).all():
        if any((server.name or "").startswith(prefix) for prefix in TEST_MCP_PREFIXES):
            server.deleted_at = now
            server.enabled = False
            server.health_status = "deleted"

    for tool in db.scalars(select(ToolDefinition).where(ToolDefinition.deleted_at.is_(None))).all():
        tool_name = tool.name or ""
        display_name = tool.display_name or ""
        is_acceptance_tool = any(tool_name.startswith(prefix) for prefix in TEST_TOOL_PREFIXES)
        is_acceptance_display = any(display_name.startswith(prefix) for prefix in TEST_MCP_PREFIXES)
        if is_acceptance_tool or is_acceptance_display:
            tool.deleted_at = now
            tool.status = "deleted"

    for skill in db.scalars(select(Skill).where(Skill.deleted_at.is_(None))).all():
        if skill.source != "system" and skill.name in TEST_SKILL_NAMES:
            skill.deleted_at = now
            skill.status = "deleted"

    for agent in db.scalars(select(Agent).where(Agent.deleted_at.is_(None))).all():
        if _is_acceptance_agent(agent):
            agent.deleted_at = now
            agent.status = "archived"

    _soft_delete_duplicate_skills(db, now)


def _soft_delete_duplicate_skills(db: Session, now) -> None:
    seen: set[tuple[str, str | None]] = set()
    query = select(Skill).where(Skill.deleted_at.is_(None)).order_by(Skill.name, Skill.created_at.desc())
    for skill in db.scalars(query).all():
        if skill.source == "system":
            continue
        key = (skill.name, skill.workspace_id)
        if key in seen and skill.name in TEST_SKILL_NAMES:
            skill.deleted_at = now
            skill.status = "deleted"
        else:
            seen.add(key)


def _is_acceptance_agent(agent: Agent) -> bool:
    extra = agent.extra or {}
    text = " ".join(
        str(value or "")
        for value in (
            agent.name,
            extra.get("display_name"),
            agent.description,
        )
    ).lower()
    return any(pattern in text for pattern in TEST_AGENT_PATTERNS)
