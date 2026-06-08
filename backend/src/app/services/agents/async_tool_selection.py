from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent, Conversation, McpServer, Skill
from app.services.agents.capability_permissions import (
    agent_uses_default_full_permissions,
    configured_mcp_server_ids,
    configured_skill_ids,
    configured_tool_names,
)
from app.services.mcp import tool_name
from app.services.tools.builtins.registry import BUILTIN_TOOLS, active_builtin_tool_names


TOOL_INTENT_PATTERN = re.compile(
    (
        r"(skill|mcp|tool|file|sandbox|run|search|deploy|analysis|generate|code|test|"
        "\u5de5\u5177|\u8c03\u7528|\u8bfb\u53d6|\u6587\u4ef6|\u6c99\u7bb1|"
        "\u547d\u4ee4|\u8fd0\u884c|\u68c0\u7d22|\u641c\u7d22|\u90e8\u7f72|"
        "\u5206\u6790|\u751f\u6210|\u4ee3\u7801|\u6d4b\u8bd5)"
    ),
    re.I,
)


def workspace_id(conversation: Conversation) -> str | None:
    extra = conversation.extra or {}
    value = extra.get("workspace_id") or extra.get("workspaceId")
    return str(value) if value else None


def score_text(prompt: str, *values: Any) -> int:
    haystack = " ".join(str(value or "") for value in values).lower()
    tokens = [
        token
        for token in re.split("[\\s,\uFF0C\u3001\uFF1B;|_\\-]+", prompt.lower())
        if len(token) >= 2
    ]
    score = 0
    for token in tokens:
        if token in haystack:
            score += 2 if len(token) > 3 else 1
    return score


def mcp_tool_args(prompt: str, name: str) -> dict[str, Any]:
    args: dict[str, Any] = {"input": prompt, "prompt": prompt}
    if name.startswith("file.") or "read" in name:
        args.setdefault("path", ".")
    if "sandbox" in name or "run" in name:
        args.setdefault("command", "echo AgentHub MCP sandbox smoke")
    if "search" in name or "retrieve" in name:
        args.setdefault("query", prompt)
    return args


async def select_skills(db: AsyncSession, conversation: Conversation, prompt: str, limit: int = 2) -> list[Skill]:
    current_workspace_id = workspace_id(conversation)
    query = select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
    query = query.where(or_(Skill.owner_id == conversation.creator_id, Skill.owner_id.is_(None)))
    if current_workspace_id:
        query = query.where(or_(Skill.workspace_id == current_workspace_id, Skill.workspace_id.is_(None)))
    else:
        query = query.where(Skill.workspace_id.is_(None))
    scored: list[tuple[int, Skill]] = []
    for skill in (await db.scalars(query)).all():
        score = score_text(prompt, skill.name, skill.description, skill.category, skill.tags, skill.content)
        if score > 0 or (TOOL_INTENT_PATTERN.search(prompt) and skill.source in {"ai", "mcp"}):
            scored.append((score + (2 if skill.source in {"ai", "mcp"} else 0), skill))
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    return [skill for score, skill in scored if score > 0][:limit]


async def select_agent_skills(db: AsyncSession, conversation: Conversation, prompt: str, agent: Agent, limit: int = 2) -> list[Skill]:
    default_all = agent_uses_default_full_permissions(agent)
    allowed_ids = configured_skill_ids(agent)
    if not allowed_ids and not default_all:
        return []
    current_workspace_id = workspace_id(conversation)
    query = select(Skill).where(Skill.deleted_at.is_(None), Skill.status == "active")
    if allowed_ids and not default_all:
        query = query.where(Skill.id.in_(allowed_ids))
    if current_workspace_id:
        query = query.where(or_(Skill.workspace_id == current_workspace_id, Skill.workspace_id.is_(None)))
    skills = (await db.scalars(query)).all()
    scored = [(score_text(prompt, skill.name, skill.description, skill.category, skill.tags, skill.content), skill) for skill in skills]
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    return [skill for _score, skill in scored][:limit]


async def select_mcp_action(db: AsyncSession, conversation: Conversation, prompt: str) -> tuple[McpServer, str] | None:
    if not TOOL_INTENT_PATTERN.search(prompt):
        return None
    current_workspace_id = workspace_id(conversation)
    query = select(McpServer).where(
        McpServer.deleted_at.is_(None),
        McpServer.enabled.is_(True),
        or_(McpServer.owner_id == conversation.creator_id, McpServer.owner_id.is_(None)),
    )
    if current_workspace_id:
        query = query.where(or_(McpServer.workspace_id == current_workspace_id, McpServer.workspace_id.is_(None)))
    best: tuple[int, McpServer, str] | None = None
    for server in (await db.scalars(query)).all():
        tools = [item for item in (server.tools or []) if isinstance(item, dict) and item.get("enabled", True)]
        if not tools:
            tools = [{"name": item, "description": "Allowed by tool_filter", "enabled": True} for item in (server.tool_filter or [])]
        for tool in tools:
            name = tool_name(tool)
            if not name:
                continue
            score = score_text(prompt, server.name, name, tool.get("description"), server.tool_filter)
            if "mcp" in prompt.lower() or "\u5de5\u5177" in prompt:
                score += 2
            if best is None or score > best[0]:
                best = (score, server, name)
    if not best or best[0] <= 0:
        return None
    return best[1], best[2]


async def select_agent_mcp_action(db: AsyncSession, conversation: Conversation, prompt: str, agent: Agent) -> tuple[McpServer, str] | None:
    default_all = agent_uses_default_full_permissions(agent)
    allowed_ids = configured_mcp_server_ids(agent)
    if (not allowed_ids and not default_all) or not TOOL_INTENT_PATTERN.search(prompt):
        return None
    current_workspace_id = workspace_id(conversation)
    query = select(McpServer).where(
        McpServer.deleted_at.is_(None),
        McpServer.enabled.is_(True),
    )
    if allowed_ids and not default_all:
        query = query.where(McpServer.id.in_(allowed_ids))
    if current_workspace_id:
        query = query.where(or_(McpServer.workspace_id == current_workspace_id, McpServer.workspace_id.is_(None)))
    best: tuple[int, McpServer, str] | None = None
    for server in (await db.scalars(query)).all():
        tools = [item for item in (server.tools or []) if isinstance(item, dict) and item.get("enabled", True)]
        if not tools:
            tools = [{"name": item, "description": "Allowed by tool_filter", "enabled": True} for item in (server.tool_filter or [])]
        for tool in tools:
            name = tool_name(tool)
            score = score_text(prompt, server.name, name, tool.get("description"), server.tool_filter)
            if best is None or score > best[0]:
                best = (score, server, name)
    return (best[1], best[2]) if best and best[0] > 0 else None


def builtin_tool_args(conversation: Conversation, prompt: str, name: str) -> dict[str, Any]:
    args: dict[str, Any] = {"input": prompt, "prompt": prompt, "conversation_id": conversation.id}
    if name.startswith("artifact.create_"):
        args.update({"title": "AgentHub Tool Artifact", "body": prompt})
        if name in {"artifact.create_html", "artifact.create_web_app"}:
            args["html"] = ""
    if name == "db.inspect":
        return {}
    if name in {"api.test", "test.run"}:
        args.setdefault("path", "/api/v1/health")
        args.setdefault("command", "pytest -q")
    if name == "sandbox.run":
        args.setdefault("command", "echo AgentHub worker sandbox")
    if name == "security.audit":
        args.setdefault("target", prompt)
    if name == "document.review":
        args.setdefault("text", prompt)
    if name == "external_agent.invoke":
        args.setdefault("action", "run")
        args.setdefault("provider", external_agent_provider_for_prompt(prompt))
    return args


def external_agent_provider_for_prompt(prompt: str) -> str:
    if re.search(r"(claude|claude\s*code|claude-code)", prompt, re.I):
        return "claude_code"
    if re.search(r"(opencode|open\s*code|open-code)", prompt, re.I):
        return "opencode"
    return "codex"


def select_agent_builtin_tools(agent: Agent, prompt: str, limit: int) -> list[str]:
    names = active_builtin_tool_names() if agent_uses_default_full_permissions(agent) else configured_tool_names(agent)
    allowed = [name for name in names if name in BUILTIN_TOOLS]
    if not allowed:
        return []
    prompt_lower = prompt.lower()
    preferred: list[str] = []
    artifact_map = [
        ("pdf", "artifact.create_pdf"),
        ("word", "artifact.create_docx"),
        ("docx", "artifact.create_docx"),
        ("excel", "artifact.create_xlsx"),
        ("xlsx", "artifact.create_xlsx"),
        ("ppt", "artifact.create_pptx"),
        ("pptx", "artifact.create_pptx"),
        ("html", "artifact.create_html"),
        ("web", "artifact.create_web_app"),
        ("\u7f51\u9875", "artifact.create_web_app"),
        ("\u9875\u9762", "artifact.create_web_app"),
    ]
    for keyword, tool in artifact_map:
        if keyword in prompt_lower and tool in allowed:
            preferred.append(tool)
    if re.search("(\u6587\u4ef6|\u9644\u4ef6|\u6458\u8981|\u8bfb\u53d6|\u89e3\u6790)", prompt, re.I):
        preferred.extend([name for name in ("file.extract_text", "file.summarize", "file.preview") if name in allowed])
    if re.search("(\u6d4b\u8bd5|api|\u63a5\u53e3)", prompt, re.I):
        preferred.extend([name for name in ("api.test", "test.run") if name in allowed])
    if re.search("(\u6570\u636e\u5e93|db|schema|\u8868)", prompt, re.I) and "db.inspect" in allowed:
        preferred.append("db.inspect")
    if re.search("(\u547d\u4ee4|\u8fd0\u884c|\u6c99\u7bb1|\u4ee3\u7801)", prompt, re.I) and "sandbox.run" in allowed:
        preferred.append("sandbox.run")
    if re.search("(\u5ba1\u67e5|\u5b89\u5168|\u98ce\u9669|\u5408\u89c4)", prompt, re.I):
        preferred.extend([name for name in ("security.audit", "document.review") if name in allowed])
    if re.search(
        "(codex|claude|opencode|open\\s*code|external\\s*(agent|coding)|coding\\s*agent|\\u5916\\u90e8|\\u667a\\u80fd\\u4f53)",
        prompt,
        re.I,
    ) and "external_agent.invoke" in allowed:
        preferred.append("external_agent.invoke")
    if not preferred and TOOL_INTENT_PATTERN.search(prompt):
        preferred = allowed[:1]
    return list(dict.fromkeys(preferred))[:limit]
