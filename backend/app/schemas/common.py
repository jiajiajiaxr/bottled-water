from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应包装器。"""

    code: int = 0
    message: str = "success"
    data: T
    timestamp: str


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserOut(ORMModel):
    id: str
    email: str
    username: str
    name: str
    display_name: str
    avatar_url: str | None = None
    role: str


class UserResponse(BaseModel):
    """/auth/me 响应模型。"""

    code: int = 0
    message: str = "success"
    data: UserOut
    timestamp: str


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


class FileAssetOut(ORMModel):
    id: str
    file_id: str
    conversation_id: str | None = None
    message_id: str | None = None
    artifact_id: str | None = None
    filename: str
    original_filename: str
    content_type: str
    size: int
    checksum: str
    purpose: str
    parse_status: str
    public_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


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


class KnowledgeBaseOut(ORMModel):
    id: str
    knowledge_base_id: str
    name: str
    description: str
    scope: str
    visibility: str
    chunk_strategy: str
    embedding_model: str
    document_count: int
    chunk_count: int
    total_tokens: int
    status: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class KnowledgeDocumentOut(ORMModel):
    id: str
    document_id: str
    knowledge_base_id: str
    file_asset_id: str | None = None
    title: str
    source_type: str
    source_uri: str
    token_count: int
    chunk_count: int
    index_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class WorkspaceMemberOut(ORMModel):
    id: str
    workspace_id: str
    user_id: str
    user_name: str | None = None
    role: str
    permissions: list[str] = Field(default_factory=list)
    joined_at: str | None = None
    left_at: str | None = None


class WorkspaceOut(ORMModel):
    id: str
    workspace_id: str
    name: str
    description: str
    type: str
    status: str
    avatar_color: str
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    workflow: dict[str, Any] = Field(default_factory=dict)
    resource_bindings: dict[str, Any] = Field(default_factory=dict)
    member_count: int
    project_count: int
    last_active_at: str | None = None
    members: list[WorkspaceMemberOut] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ProjectOut(ORMModel):
    id: str
    project_id: str
    workspace_id: str
    name: str
    description: str
    type: str
    status: str
    tags: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    file_count: int
    current_version: int
    created_at: str
    updated_at: str


class ProjectFileOut(ORMModel):
    id: str
    file_id: str
    project_id: str
    path: str
    language: str
    checksum: str | None = None
    size: int
    version: int
    content: str | None = None
    created_at: str
    updated_at: str


class PromptTemplateOut(ORMModel):
    id: str
    name: str
    description: str
    scope: str
    category: str
    content: str
    variables: list[str] = Field(default_factory=list)
    version: str
    status: str
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class ShortcutCommandOut(ORMModel):
    id: str
    name: str
    description: str
    prompt_template: str
    agent_route: dict[str, Any] = Field(default_factory=dict)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    status: str
    workspace_id: str | None = None
    created_at: str
    updated_at: str


class SkillOut(ORMModel):
    id: str
    skill_id: str
    workspace_id: str | None = None
    name: str
    description: str
    category: str
    source: str
    status: str
    version: str
    content: str
    prompt: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None
    created_at: str
    updated_at: str


class ToolDefinitionOut(ORMModel):
    id: str
    tool_id: str
    workspace_id: str | None = None
    name: str
    display_name: str
    description: str
    category: str
    type: str
    status: str
    version: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    implementation: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_builtin: bool
    created_by: str | None = None
    created_at: str
    updated_at: str


class ModelProviderOut(ORMModel):
    id: str
    name: str
    provider_type: str
    base_url: str
    api_key_set: bool
    api_key_ref: str | None = None
    default_model: str
    status: str
    supports_streaming: bool
    supports_embeddings: bool
    config: dict[str, Any] = Field(default_factory=dict)
    model_count: int
    created_at: str
    updated_at: str


class ModelConfigOut(ORMModel):
    id: str
    provider_id: str
    provider_name: str | None = None
    name: str
    model_id: str
    purpose: str
    context_window: int
    max_output_tokens: int
    temperature_default: float
    status: str
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class McpServerOut(ORMModel):
    id: str
    workspace_id: str | None = None
    name: str
    transport: str
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    enabled: bool
    tool_filter: list[str] = Field(default_factory=list)
    timeout_ms: int
    retry: int
    health_status: str
    last_checked_at: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    created_by: str | None = None
    created_at: str
    updated_at: str


class McpInvocationOut(ORMModel):
    id: str
    server_id: str
    workspace_id: str | None = None
    conversation_id: str | None = None
    tool_name: str
    transport: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    duration_ms: int
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class WorkflowRunOut(ORMModel):
    id: str
    conversation_id: str
    trigger_message_id: str | None = None
    status: str
    mode: str
    workflow_snapshot: dict[str, Any] = Field(default_factory=dict)
    node_states: list[dict[str, Any]] = Field(default_factory=list)
    edge_states: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    progress: int
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class SandboxOut(ORMModel):
    id: str
    workspace_id: str | None = None
    project_id: str | None = None
    name: str
    image: str
    status: str
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    mounted_files: list[dict[str, Any]] = Field(default_factory=list)
    command_history: list[dict[str, Any]] = Field(default_factory=list)
    last_command_at: str | None = None
    expires_at: str | None = None
    created_at: str
    updated_at: str


class RemoteConnectionOut(ORMModel):
    id: str
    workspace_id: str | None = None
    name: str
    connection_type: str
    endpoint: str
    status: str
    capabilities: list[str] = Field(default_factory=list)
    session_state: dict[str, Any] = Field(default_factory=dict)
    last_connected_at: str | None = None
    created_at: str
    updated_at: str


# ----- 通用列表/分页包装器 -----


class ListItems(BaseModel):
    items: list[Any]
    total: int


class PaginatedItems(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_more: bool = False


class MessageResponse(BaseModel):
    message: str


class OkResponse(BaseModel):
    ok: bool

