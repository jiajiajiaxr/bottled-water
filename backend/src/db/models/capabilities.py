from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, uuid_str
from ..types import ContentJSON, EncryptedText, SensitiveJSON

if TYPE_CHECKING:
    pass


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="general", index=True)
    source: Mapped[str] = mapped_column(String(40), default="manual", index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    content: Mapped[str] = mapped_column(EncryptedText, default="")
    prompt: Mapped[str] = mapped_column(EncryptedText, default="")
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)


class SkillRun(Base, TimestampMixin):
    __tablename__ = "skill_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id"), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True, index=True
    )
    runtime_type: Mapped[str] = mapped_column(String(40), default="prompt_skill", index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    input: Mapped[dict] = mapped_column(ContentJSON, default=dict)
    output: Mapped[dict] = mapped_column(ContentJSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)


class ToolDefinition(Base, TimestampMixin):
    __tablename__ = "tool_definitions"
    __table_args__ = (UniqueConstraint("owner_id", "workspace_id", "name", name="uq_tool_owner_workspace_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="custom", index=True)
    type: Mapped[str] = mapped_column(String(60), default="custom_python", index=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    builtin_handler: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    input_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, default=dict)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    implementation: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    runtime: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class ToolInvocation(Base, TimestampMixin):
    __tablename__ = "tool_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    tool_id: Mapped[str | None] = mapped_column(ForeignKey("tool_definitions.id"), nullable=True, index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(200), index=True)
    tool_type: Mapped[str] = mapped_column(String(60), default="builtin", index=True)
    arguments: Mapped[dict] = mapped_column(ContentJSON, default=dict)
    result: Mapped[dict] = mapped_column(ContentJSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    error_message: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)


class ExternalAgentRun(Base, TimestampMixin):
    __tablename__ = "external_agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    command: Mapped[list] = mapped_column(SensitiveJSON, default=list)
    cwd: Mapped[str] = mapped_column(Text, default="")
    input_prompt: Mapped[str] = mapped_column(EncryptedText, default="")
    stdout_tail: Mapped[str] = mapped_column(EncryptedText, default="")
    stderr_tail: Mapped[str] = mapped_column(EncryptedText, default="")
    changed_files: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)


class ModelProvider(Base, TimestampMixin):
    __tablename__ = "model_providers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    provider_type: Mapped[str] = mapped_column(String(60), default="openai_compatible", index=True)
    base_url: Mapped[str] = mapped_column(Text)
    api_key_ref: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    default_model: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=True)
    supports_embeddings: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)

    models: Mapped[list["ModelConfig"]] = relationship(back_populates="provider", cascade="all, delete-orphan")


class ModelConfig(Base, TimestampMixin):
    __tablename__ = "model_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider_id: Mapped[str] = mapped_column(ForeignKey("model_providers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    model_id: Mapped[str] = mapped_column(String(200), index=True)
    purpose: Mapped[str] = mapped_column(String(60), default="chat", index=True)
    context_window: Mapped[int] = mapped_column(Integer, default=128000)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=8192)
    temperature_default: Mapped[float] = mapped_column(Float, default=0.7)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    config: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)

    provider: Mapped["ModelProvider"] = relationship(back_populates="models")


class McpServer(Base, TimestampMixin):
    __tablename__ = "mcp_servers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    transport: Mapped[str] = mapped_column(String(40), default="httpStream", index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    args: Mapped[list] = mapped_column(JSON, default=list)
    env: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    headers: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    tool_filter: Mapped[list] = mapped_column(JSON, default=list)
    timeout_ms: Mapped[int] = mapped_column(Integer, default=30000)
    retry: Mapped[int] = mapped_column(Integer, default=1)
    health_status: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tools: Mapped[list] = mapped_column(JSON, default=list)
    extra: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class McpToolInvocation(Base, TimestampMixin):
    __tablename__ = "mcp_tool_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    server_id: Mapped[str] = mapped_column(ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(200), index=True)
    transport: Mapped[str] = mapped_column(String(40), default="httpStream", index=True)
    arguments: Mapped[dict] = mapped_column(ContentJSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    result: Mapped[dict] = mapped_column(ContentJSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)

    server: Mapped["McpServer"] = relationship()


class SandboxSession(Base, TimestampMixin):
    __tablename__ = "sandbox_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    image: Mapped[str] = mapped_column(String(200), default="python:3.11-slim")
    status: Mapped[str] = mapped_column(String(40), default="ready", index=True)
    resource_limits: Mapped[dict] = mapped_column(JSON, default=dict)
    mounted_files: Mapped[list] = mapped_column(SensitiveJSON, default=list)
    command_history: Mapped[list] = mapped_column(ContentJSON, default=list)
    last_command_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)


class RemoteConnection(Base, TimestampMixin):
    __tablename__ = "remote_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    connection_type: Mapped[str] = mapped_column(String(40), default="browser", index=True)
    endpoint: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="disconnected", index=True)
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    credentials_ref: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    session_state: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)
