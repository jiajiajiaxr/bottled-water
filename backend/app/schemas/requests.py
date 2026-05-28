from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = "demo"
    password: str = "agenthub"


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    display_name: str | None = None


class CreateConversationRequest(BaseModel):
    chat_type: Literal["single", "group"] = "single"
    title: str | None = None
    description: str | None = None
    participant_agent_ids: list[str] = Field(default_factory=list)


class UpdateConversationRequest(BaseModel):
    action: Literal["pin", "unpin", "archive", "unarchive", "rename"]
    title: str | None = None


class SendMessageRequest(BaseModel):
    client_message_id: str
    content_type: str = "text"
    content: dict[str, Any]
    reply_to_message_id: str | None = None


class CreateAgentRequest(BaseModel):
    name: str
    type: str = "custom"
    description: str = ""
    display_name: str | None = None
    avatar_url: str | None = None
    avatar_color: str | None = None
    provider: str = "custom"
    version: str = "1.0"
    capabilities: list[Any] = Field(default_factory=list)
    system_prompt: str = ""
    base_agent_id: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)


class UpdateAgentRequest(BaseModel):
    name: str | None = None
    display_name: str | None = None
    description: str | None = None
    status: str | None = None
    avatar_url: str | None = None
    avatar_color: str | None = None
    capabilities: list[Any] | None = None
    system_prompt: str | None = None
    config: dict[str, Any] | None = None
    tools: list[str] | None = None


class ParseCapabilitiesRequest(BaseModel):
    text: str


class GenerateAgentRequest(BaseModel):
    brief: str
    base_agent_id: str | None = None
    preferred_tools: list[str] = Field(default_factory=list)


class TestAgentRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class AddParticipantRequest(BaseModel):
    agent_ids: list[str] = Field(default_factory=list)
    user_ids: list[str] = Field(default_factory=list)
    role: str = "member"


class InviteParticipantRequest(BaseModel):
    invitee_email: str | None = None
    agent_ids: list[str] = Field(default_factory=list)
    role: str = "member"


class ArtifactEditRequest(BaseModel):
    files: dict[str, str]
    change_summary: str = "用户在线编辑"


class DiffRequest(BaseModel):
    old_version: int | None = None
    new_version: int | None = None


class CreateDeploymentRequest(BaseModel):
    artifact_id: str
    mode: str = "preview_link"
    config: dict[str, Any] = Field(default_factory=dict)


class CreateKnowledgeBaseRequest(BaseModel):
    name: str
    description: str = ""
    scope: str = "personal"
    visibility: str = "private"
    config: dict[str, Any] = Field(default_factory=dict)


class ImportKnowledgeTextRequest(BaseModel):
    title: str
    content: str
    source_type: str = "manual"
    source_uri: str = ""


class RetrieveKnowledgeRequest(BaseModel):
    query: str
    top_k: int = 5
    mode: str = "hybrid"
    similarity_threshold: float = 0.0


class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""
    type: str = "custom"
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    workflow: dict[str, Any] = Field(default_factory=dict)


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    config: dict[str, Any] | None = None
    workflow: dict[str, Any] | None = None
    resource_bindings: dict[str, Any] | None = None


class AddWorkspaceMemberRequest(BaseModel):
    user_id: str
    role: str = "member"
    permissions: list[str] = Field(default_factory=list)


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    type: str = "code_project"
    tags: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class UpsertProjectFileRequest(BaseModel):
    path: str
    content: str
    language: str = "text"


class CreatePromptTemplateRequest(BaseModel):
    name: str
    description: str = ""
    scope: str = "workspace"
    category: str = "general"
    content: str
    variables: list[str] = Field(default_factory=list)


class CreateShortcutCommandRequest(BaseModel):
    name: str
    description: str = ""
    prompt_template: str
    agent_route: dict[str, Any] = Field(default_factory=dict)
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class CreateSkillRequest(BaseModel):
    workspace_id: str | None = None
    name: str
    description: str = ""
    category: str = "general"
    source: Literal["manual", "mcp", "ai"] = "manual"
    status: str = "active"
    version: str = "1.0.0"
    content: str = ""
    prompt: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    manifest: dict[str, Any] = Field(default_factory=dict)


class UpdateSkillRequest(BaseModel):
    workspace_id: str | None = None
    name: str | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    version: str | None = None
    content: str | None = None
    prompt: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    tools: list[dict[str, Any]] | None = None
    tags: list[str] | None = None
    config: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None


class ImportMcpSkillRequest(BaseModel):
    mcp_server_id: str
    workspace_id: str | None = None
    tool_names: list[str] = Field(default_factory=list)
    name: str | None = None
    description: str | None = None
    category: str = "mcp"
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class GenerateSkillRequest(BaseModel):
    workspace_id: str | None = None
    name: str | None = None
    intent: str
    requirements: str = ""
    category: str = "ai"
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class TestSkillRequest(BaseModel):
    input: Any = ""
    message: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class CreateToolRequest(BaseModel):
    workspace_id: str | None = None
    name: str
    display_name: str | None = None
    description: str = ""
    category: str = "custom"
    type: str = "custom_python"
    status: str = "active"
    version: str = "1.0.0"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    implementation: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateToolRequest(BaseModel):
    workspace_id: str | None = None
    display_name: str | None = None
    description: str | None = None
    category: str | None = None
    status: str | None = None
    version: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    permissions: list[str] | None = None
    implementation: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    tags: list[str] | None = None
    config: dict[str, Any] | None = None


class GenerateToolRequest(BaseModel):
    workspace_id: str | None = None
    name: str | None = None
    intent: str
    requirements: str = ""
    category: str = "custom"
    allowed_permissions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class InvokeToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    workspace_id: str | None = None


class CreateModelProviderRequest(BaseModel):
    name: str
    provider_type: str = "openai_compatible"
    base_url: str
    api_key: str | None = None
    default_model: str
    supports_streaming: bool = True
    supports_embeddings: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


class CreateModelConfigRequest(BaseModel):
    provider_id: str
    name: str
    model_id: str
    purpose: str = "chat"
    context_window: int = 128000
    max_output_tokens: int = 8192
    temperature_default: float = 0.7
    config: dict[str, Any] = Field(default_factory=dict)


class TestModelRequest(BaseModel):
    prompt: str = "你好，请用一句话介绍你自己。"
    model_config_id: str | None = None


class CreateMcpServerRequest(BaseModel):
    workspace_id: str | None = None
    name: str
    transport: str = "httpStream"
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    tool_filter: list[str] = Field(default_factory=list)
    timeout_ms: int = 30000
    retry: int = 1


class ImportMcpServerRequest(BaseModel):
    workspace_id: str | None = None
    source_type: Literal["manifest_url", "json"] = "json"
    source: str


class InvokeMcpToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    conversation_id: str | None = None
    timeout_ms: int | None = None


class CreateSandboxRequest(BaseModel):
    workspace_id: str | None = None
    project_id: str | None = None
    name: str
    image: str = "python:3.11-slim"
    resource_limits: dict[str, Any] = Field(default_factory=dict)


class RunSandboxCommandRequest(BaseModel):
    command: str
    timeout_seconds: int = 30
    workdir: str = ""
    cwd: str | None = None


class CreateRemoteConnectionRequest(BaseModel):
    workspace_id: str | None = None
    name: str
    connection_type: str = "browser"
    endpoint: str = ""
    capabilities: list[str] = Field(default_factory=list)
