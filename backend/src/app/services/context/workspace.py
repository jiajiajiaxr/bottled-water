from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Agent, Artifact, Conversation, FileAsset, McpServer, Skill, ToolDefinition, Workspace
from app.services.agents.capability_permissions import (
    agent_uses_default_full_permissions,
    configured_tool_names,
)
from app.services.context.compression import trim_text
from app.services.context.memory import workspace_memory_text
from app.services.context.variables import artifact_reference_scope
from app.services.tools.builtins.registry import BUILTIN_TOOLS, active_builtin_tool_names
from app.services.tools.catalog import sync_builtin_tool_definitions


@dataclass
class WorkspaceContext:
    workspace_id: str | None = None
    long_term_memory: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    authorized_tools: list[dict[str, Any]] = field(default_factory=list)
    authorized_skills: list[dict[str, Any]] = field(default_factory=list)
    authorized_mcp_servers: list[dict[str, Any]] = field(default_factory=list)

    def as_scope(self) -> dict[str, Any]:
        return {
            "workspace": self.to_dict(),
            "artifact": artifact_reference_scope(self.artifacts),
            "artifacts": artifact_reference_scope(self.artifacts),
            "files": {item["id"]: item for item in self.files if item.get("id")},
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "long_term_memory": self.long_term_memory,
            "files": self.files,
            "artifacts": self.artifacts,
            "authorized_tools": self.authorized_tools,
            "authorized_skills": self.authorized_skills,
            "authorized_mcp_servers": self.authorized_mcp_servers,
        }

    def to_text(self) -> str:
        parts: list[str] = []
        if self.long_term_memory:
            parts.append("工作区长期记忆：\n" + self.long_term_memory)
        if self.files:
            parts.append("当前会话文件：\n" + "\n".join(f"- {item['filename']}: {item['summary']}" for item in self.files))
        if self.artifacts:
            parts.append(
                "当前会话产物：\n"
                + "\n".join(
                    f"- {item['title']} ({item['format']}): {item['preview_url']}" for item in self.artifacts
                )
            )
        if self.authorized_tools:
            parts.append(
                "当前 Agent 已授权 Tool 摘要：\n"
                + "\n".join(f"- {item['name']}: {item['description']}" for item in self.authorized_tools)
            )
        if self.authorized_skills:
            parts.append(
                "当前 Agent 已授权 Skill 摘要：\n"
                + "\n".join(f"- {item['name']}: {item['description']}" for item in self.authorized_skills)
            )
        if self.authorized_mcp_servers:
            parts.append(
                "当前 Agent 已授权 MCP 摘要：\n"
                + "\n".join(f"- {item['name']}: {item['tools']}" for item in self.authorized_mcp_servers)
            )
        return trim_text("\n\n".join(parts), max_chars=8000)


def build_workspace_context(
    db: Session,
    conversation: Conversation,
    *,
    agent: Agent | None = None,
) -> WorkspaceContext:
    workspace_id = _workspace_id(conversation)
    workspace = db.get(Workspace, workspace_id) if workspace_id else None
    return WorkspaceContext(
        workspace_id=workspace_id,
        long_term_memory=workspace_memory_text(workspace),
        files=_files(db, conversation),
        artifacts=_artifacts(db, conversation),
        authorized_tools=_authorized_tools(db, agent),
        authorized_skills=_authorized_skills(db, agent),
        authorized_mcp_servers=_authorized_mcp_servers(db, agent),
    )


def _workspace_id(conversation: Conversation) -> str | None:
    extra = conversation.extra if isinstance(conversation.extra, dict) else {}
    value = extra.get("workspace_id") or extra.get("workspaceId")
    return str(value) if value else None


def _files(db: Session, conversation: Conversation) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(FileAsset)
        .where(
            FileAsset.conversation_id == conversation.id,
            FileAsset.deleted_at.is_(None),
        )
        .order_by(FileAsset.updated_at.desc())
        .limit(12)
    ).all()
    return [
        {
            "id": item.id,
            "filename": item.original_filename,
            "content_type": item.content_type,
            "summary": _file_summary(item),
            "parse_status": item.parse_status,
        }
        for item in rows
    ]


def _artifacts(db: Session, conversation: Conversation) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(Artifact)
        .where(Artifact.conversation_id == conversation.id, Artifact.deleted_at.is_(None))
        .order_by(Artifact.updated_at.desc())
        .limit(12)
    ).all()
    return [
        {
            "id": item.id,
            "artifact_id": item.id,
            "title": item.name,
            "format": (item.content or {}).get("format") or item.type,
            "preview_url": f"/api/v1/artifacts/{item.id}/preview",
            "export_url": f"/api/v1/artifacts/{item.id}/export",
        }
        for item in rows
    ]


def _authorized_tools(db: Session, agent: Agent | None) -> list[dict[str, Any]]:
    if not agent:
        return []
    default_all = agent_uses_default_full_permissions(agent)
    allowed = active_builtin_tool_names() if default_all else configured_tool_names(agent)
    if not allowed:
        return []
    sync_builtin_tool_definitions(db)
    rows = db.scalars(
        select(ToolDefinition)
        .where(
            ToolDefinition.deleted_at.is_(None),
            ToolDefinition.status == "active",
            (ToolDefinition.name.in_(allowed)) | (ToolDefinition.id.in_(allowed)),
        )
        .order_by(ToolDefinition.name.asc())
        .limit(40)
    ).all()
    items = [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description or item.display_name or "",
            "type": item.type,
        }
        for item in rows
    ]
    seen = {item["name"] for item in items}
    for name in allowed:
        builtin = BUILTIN_TOOLS.get(name)
        if builtin and name not in seen:
            items.append({"id": name, "name": name, "description": builtin.description, "type": "builtin"})
    return items[:40]


def _authorized_skills(db: Session, agent: Agent | None) -> list[dict[str, Any]]:
    allowed = [str(item) for item in (agent.config or {}).get("skill_ids") or [] if item] if agent else []
    if not allowed:
        return []
    rows = db.scalars(
        select(Skill)
        .where(Skill.id.in_(allowed), Skill.deleted_at.is_(None), Skill.status == "active")
        .order_by(Skill.updated_at.desc())
        .limit(10)
    ).all()
    return [{"id": item.id, "name": item.name, "description": item.description} for item in rows]


def _authorized_mcp_servers(db: Session, agent: Agent | None) -> list[dict[str, Any]]:
    allowed = [str(item) for item in (agent.config or {}).get("mcp_server_ids") or [] if item] if agent else []
    if not allowed:
        return []
    query = select(McpServer).where(
        McpServer.id.in_(allowed),
        McpServer.deleted_at.is_(None),
        McpServer.enabled.is_(True),
    )
    if agent:
        query = query.where(or_(McpServer.owner_id == agent.owner_id, McpServer.owner_id.is_(None)))
    rows = db.scalars(query.order_by(McpServer.updated_at.desc()).limit(10)).all()
    return [
        {
            "id": item.id,
            "name": item.name,
            "tools": [tool.get("name") for tool in item.tools or [] if isinstance(tool, dict)],
        }
        for item in rows
    ]


def _file_summary(asset: FileAsset) -> str:
    if asset.extracted_text:
        return trim_text(asset.extracted_text, max_chars=800)
    if asset.content_type.startswith("image/"):
        return "图片附件；当前未启用视觉解析。"
    return "未提取到可读文本。"
