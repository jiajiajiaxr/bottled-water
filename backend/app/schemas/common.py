from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None
    timestamp: str


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: str
    email: str
    username: str
    display_name: str
    avatar_url: str | None = None
    role: str


class AgentOut(ORMModel):
    id: str
    name: str
    type: str
    status: str
    description: str = ""
    avatar_url: str | None = None
    capabilities: list[str] = Field(default_factory=list)


class ConversationParticipantOut(BaseModel):
    agent_id: str | None = None
    agent_name: str | None = None
    agent_type: str | None = None
    agent_avatar_url: str | None = None
    role: str = "member"
    joined_at: datetime | None = None


class ConversationOut(ORMModel):
    id: str
    chat_type: str
    title: str
    description: str = ""
    avatar_url: str | None = None
    status: str
    is_pinned: bool
    pinned_at: datetime | None = None
    unread_count: int
    last_message_preview: str
    last_message_sender: str
    last_message_at: datetime | None = None
    activity_score: int
    message_count: int
    created_at: datetime
    updated_at: datetime
    participants: list[ConversationParticipantOut] = Field(default_factory=list)


class MessageOut(ORMModel):
    id: str
    client_message_id: str | None = None
    conversation_id: str
    sender_type: str
    sender_id: str | None = None
    sender_name: str
    sender_avatar_url: str | None = None
    content_type: str
    content: dict[str, Any]
    status: str
    reply_to_message_id: str | None = None
    version_count: int
    current_version: int
    created_at: datetime
    updated_at: datetime


class TaskOut(ORMModel):
    id: str
    conversation_id: str | None
    title: str
    description: str
    status: str
    priority: str
    progress: int
    plan: dict[str, Any]
    output: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class SubtaskOut(ORMModel):
    id: str
    parent_task_id: str
    title: str
    description: str
    status: str
    order_index: int
    agent_id: str | None
    output: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ArtifactOut(ORMModel):
    id: str
    conversation_id: str
    task_id: str | None = None
    agent_id: str | None = None
    type: str
    name: str
    description: str
    status: str
    storage_url: str
    content: dict[str, Any]
    current_version: int
    created_at: datetime
    updated_at: datetime


class DeploymentOut(ORMModel):
    id: str
    artifact_id: str
    mode: str
    status: str
    access_url: str | None = None
    deploy_log: str
    steps: list[dict[str, Any]]
    error_message: str | None = None
    deployed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

