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
    default_model_config_id: str | None = None


class UserResponse(BaseModel):
    """/auth/me 响应模型。"""

    code: int = 0
    message: str = "success"
    data: UserOut
    timestamp: str


class AgentCapabilityOut(BaseModel):
    """Agent 能力项。"""

    id: str
    label: str
    category: str
    proficiency: int


class AgentConfigOut(BaseModel):
    """Agent 运行时配置。"""

    max_context_tokens: int = 128000
    max_output_tokens: int = 8192
    supports_streaming: bool = True
    supports_vision: bool = False
    supports_tool_use: bool = True
    supports_file_upload: bool = True
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 200000
    temperature: float = 0.7
    custom_prompt_prefix: str | None = None
    custom_parameters: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    mcp_server_ids: list[str] = Field(default_factory=list)
    agentic_loop: dict[str, Any] = Field(default_factory=dict)
    base_agent_id: str | None = None
    model_config_id: str | None = None
    model_id: str | None = None
    provider_id: str | None = None


class AgentStatsOut(BaseModel):
    """Agent 统计信息。"""

    total_conversations: int = 0
    total_messages: int = 0
    total_tokens_consumed: int = 0
    avg_response_time_ms: int = 900
    success_rate: float = 0.98
    last_active_at: str | None = None


class AgentOut(ORMModel):
    id: str
    name: str
    display_name: str
    type: str
    version: str
    status: str
    status_detail: str | None = None
    description: str = ""
    avatar_url: str | None = None
    avatar_color: str = "#1677ff"
    icon_url: str | None = None
    capabilities: list[AgentCapabilityOut] = Field(default_factory=list)
    supported_content_types: list[str] = Field(default_factory=lambda: ["text", "code", "image", "file", "card", "diff"])
    provider: str
    is_official: bool
    created_by: str | None = None
    last_heartbeat_at: str | None = None
    response_latency_ms: int = 900
    config: AgentConfigOut = Field(default_factory=AgentConfigOut)
    stats: AgentStatsOut = Field(default_factory=AgentStatsOut)
    tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ConversationParticipantOut(BaseModel):
    id: str | None = None
    participant_id: str | None = None
    participant_type: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    agent_type: str | None = None
    agent_avatar_url: str | None = None
    agent_status: str | None = None
    role: str = "member"
    nickname: str | None = None
    unread_count: int = 0
    left_at: str | None = None
    joined_at: str | None = None


class ConversationOut(ORMModel):
    id: str
    conversation_id: str
    chat_type: str
    type: str
    conversation_number: str | None = None
    group_number: str | None = None
    title: str
    description: str = ""
    workspace_id: str | None = None
    avatar_url: str | None = None
    participants: list[ConversationParticipantOut] = Field(default_factory=list)
    participant_names: list[str] = Field(default_factory=list)
    participant_count: int = 0
    agent_count: int = 0
    user_count: int = 0
    master_enabled: bool = False
    max_participants: int = 8
    status: str
    is_pinned: bool
    pinned: bool = False
    pinned_at: str | None = None
    unread_count: int = 0
    unread: int = 0
    last_message_preview: str = ""
    last_message: str = ""
    last_message_sender: str = ""
    last_message_at: str | None = None
    updated_at: str | None = None
    activity_score: int = 0
    message_count: int = 0
    archived: bool = False
    tags: list[str] = Field(default_factory=list)
    category: str = "Default"
    folder: str = "Default"
    remark: str = ""
    workflow: dict[str, Any] | None = None
    workflow_runtime: dict[str, Any] | None = None
    created_at: str


class MessageOut(ORMModel):
    id: str
    message_id: str
    client_message_id: str | None = None
    conversation_id: str
    conversation_id_alias: str | None = Field(None, alias="conversationId")
    sender_type: str
    sender_id: str | None = None
    sender_name: str
    sender_avatar_url: str | None = None
    role: str = ""
    author: str = ""
    content_type: str
    kind: str = ""
    content: str = ""
    raw_content: dict[str, Any] = Field(default_factory=dict)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    thinking: str | None = None
    status: str
    reply_to_message_id: str | None = None
    quoted_message_id: str | None = None
    version_count: int = 0
    current_version: int = 0
    created_at: str
    created_at_alias: str | None = Field(None, alias="createdAt")
    updated_at: str


class ArtifactOut(ORMModel):
    id: str
    artifact_id: str
    conversation_id: str
    conversation_id_alias: str | None = Field(None, alias="conversationId")
    task_id: str | None = None
    agent_id: str | None = None
    type: str
    kind: str = ""
    name: str
    title: str = ""
    description: str
    status: str
    storage_url: str
    preview_url: str = ""
    export_url: str = ""
    format: str = ""
    filename: str = ""
    media_type: str = ""
    content: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, Any] = Field(default_factory=dict)
    code: str = ""
    previous_code: str = ""
    language: str = "html"
    current_version: int
    updated_at: str | None = None
    created_at: str


class LoginOut(BaseModel):
    """登录响应数据。"""

    access_token: str
    token: str
    user: UserOut


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
    health: dict[str, Any] = Field(default_factory=dict)
    health_status: str | None = None
    last_health_check_at: str | None = None
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


class ListItems(BaseModel, Generic[T]):
    items: list[T]
    total: int


class PaginatedItems(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int = 0
    has_more: bool = False
    has_next: bool = False
    has_prev: bool = False


class MessageResponse(BaseModel):
    message: str


class OkResponse(BaseModel):
    ok: bool
    changed: bool | None = None


class IdDeletedOut(BaseModel):
    """删除操作响应。"""

    id: str
    deleted: bool


class AgentStatusItemOut(BaseModel):
    """Agent 状态摘要。"""

    status: str
    name: str


class AgentCapabilityItemOut(BaseModel):
    """全局能力聚合项。"""

    label: str
    category: str
    agent_count: int
    max_proficiency: int


class AgentTestOut(BaseModel):
    """Agent 测试结果。"""

    agent: AgentOut
    request: str
    response: str
    model: str
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = 0


class FrontendLogEntry(BaseModel):
    """前端单条日志条目。"""

    timestamp: str
    level: str
    module: str
    message: str
    data: dict[str, Any] | None = None
    url: str | None = None
    user_agent: str | None = None


class FrontendLogBatch(BaseModel):
    """前端批量日志请求体。"""

    logs: list[FrontendLogEntry]

