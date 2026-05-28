from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Artifact, Conversation, FileAsset, McpServer, Skill, ToolDefinition
from app.services.context.compression import trim_text
from app.services.context.variables import artifact_reference_scope


@dataclass
class WorkspaceContext:
    workspace_id: str | None = None
    files: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)

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
            "files": self.files,
            "artifacts": self.artifacts,
            "tools": self.tools,
            "skills": self.skills,
            "mcp_servers": self.mcp_servers,
        }

    def to_text(self) -> str:
        parts: list[str] = []
        if self.files:
            parts.append("Files:\n" + "\n".join(f"- {item['filename']}: {item['summary']}" for item in self.files))
        if self.artifacts:
            parts.append(
                "Artifacts:\n"
                + "\n".join(
                    f"- {item['title']} ({item['format']}): {item['preview_url']}" for item in self.artifacts
                )
            )
        if self.tools:
            parts.append("Tools:\n" + "\n".join(f"- {item['name']}: {item['description']}" for item in self.tools))
        if self.skills:
            parts.append("Skills:\n" + "\n".join(f"- {item['name']}: {item['description']}" for item in self.skills))
        if self.mcp_servers:
            parts.append("MCP:\n" + "\n".join(f"- {item['name']}: {item['tools']}" for item in self.mcp_servers))
        return trim_text("\n\n".join(parts), max_chars=8000)


def build_workspace_context(db: Session, conversation: Conversation) -> WorkspaceContext:
    workspace_id = _workspace_id(conversation)
    return WorkspaceContext(
        workspace_id=workspace_id,
        files=_files(db, conversation),
        artifacts=_artifacts(db, conversation),
        tools=_tools(db, conversation, workspace_id),
        skills=_skills(db, conversation, workspace_id),
        mcp_servers=_mcp_servers(db, conversation, workspace_id),
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


def _tools(db: Session, conversation: Conversation, workspace_id: str | None) -> list[dict[str, Any]]:
    query = select(ToolDefinition).where(ToolDefinition.deleted_at.is_(None), ToolDefinition.status == "active")
    if workspace_id:
        query = query.where(or_(ToolDefinition.workspace_id == workspace_id, ToolDefinition.workspace_id.is_(None)))
    else:
        query = query.where(ToolDefinition.workspace_id.is_(None))
    return [
        {"id": item.id, "name": item.name, "description": item.description or item.display_name or ""}
        for item in db.scalars(query.order_by(ToolDefinition.is_builtin.desc(), ToolDefinition.name.asc()).limit(20)).all()
    ]


def _skills(db: Session, conversation: Conversation, workspace_id: str | None) -> list[dict[str, Any]]:
    query = select(Skill).where(
        Skill.deleted_at.is_(None),
        Skill.status == "active",
        or_(Skill.owner_id == conversation.creator_id, Skill.owner_id.is_(None)),
    )
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    else:
        query = query.where(Skill.workspace_id.is_(None))
    return [
        {"id": item.id, "name": item.name, "description": item.description}
        for item in db.scalars(query.order_by(Skill.updated_at.desc()).limit(10)).all()
    ]


def _mcp_servers(db: Session, conversation: Conversation, workspace_id: str | None) -> list[dict[str, Any]]:
    query = select(McpServer).where(
        McpServer.deleted_at.is_(None),
        McpServer.enabled.is_(True),
        or_(McpServer.owner_id == conversation.creator_id, McpServer.owner_id.is_(None)),
    )
    if workspace_id:
        query = query.where(or_(McpServer.workspace_id == workspace_id, McpServer.workspace_id.is_(None)))
    else:
        query = query.where(McpServer.workspace_id.is_(None))
    return [
        {"id": item.id, "name": item.name, "tools": [tool.get("name") for tool in item.tools or [] if isinstance(tool, dict)]}
        for item in db.scalars(query.order_by(McpServer.updated_at.desc()).limit(10)).all()
    ]


def _file_summary(asset: FileAsset) -> str:
    if asset.extracted_text:
        return trim_text(asset.extracted_text, max_chars=800)
    if asset.content_type.startswith("image/"):
        return "图片附件；当前未启用视觉解析。"
    return "未提取到可读文本。"
