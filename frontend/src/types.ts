export type MessageRole = "user" | "assistant" | "system" | "tool";
export type MessageKind = "text" | "code" | "file" | "event" | "error" | "preview_card" | "diff_panel" | "deploy_status_card";
export type StreamState = "idle" | "streaming" | "done" | "error";

export interface User {
  id: string;
  name: string;
  avatar?: string;
  role: "demo" | "member" | "admin" | string;
}

export interface Conversation {
  id: string;
  chat_type?: "single" | "group";
  title: string;
  participants: Participant[];
  participant_count?: number;
  agent_count?: number;
  user_count?: number;
  master_enabled?: boolean;
  updatedAt: string;
  pinned: boolean;
  archived: boolean;
  unread: number;
  tags: string[];
  category?: string;
  folder?: string;
  remark?: string;
  workspace_id?: string;
  lastMessage: string;
  workflow?: ConversationWorkflow;
  workflow_runtime?: WorkflowRun;
}

export interface WorkflowNode {
  id: string;
  title: string;
  type?: "start" | "agent" | "tool" | "skill" | "mcp" | "condition" | "loop" | "review" | "artifact" | "end" | string;
  role?: string;
  status?: string;
  meta?: string;
  agent_id?: string;
  config?: Record<string, unknown>;
}

export interface ConversationWorkflow {
  conversation_id?: string;
  mode: string;
  nodes: WorkflowNode[];
  edges: string[][];
  settings?: Record<string, unknown>;
}

export interface WorkflowRun {
  id: string;
  conversation_id: string;
  status: string;
  mode: string;
  workflow_snapshot: ConversationWorkflow;
  node_states: Array<WorkflowNode & { progress?: number; output?: Record<string, unknown>; message?: string; started_at?: string; completed_at?: string }>;
  edge_states: Array<{ from: string; to: string; status: string }>;
  events: Array<Record<string, unknown>>;
  progress: number;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface AgentTask {
  id: string;
  task_id?: string;
  conversation_id?: string;
  title: string;
  description?: string;
  status: string;
  priority?: string;
  progress?: number;
  plan?: Record<string, unknown>;
  output?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface Participant {
  id?: string;
  participant_id?: string;
  participant_type?: "agent" | "user";
  user_id?: string;
  agent_id?: string;
  agent_name?: string;
  agent_type?: string;
  agent_status?: string;
  agent_avatar_url?: string;
  role?: "owner" | "admin" | "member";
  nickname?: string;
  joined_at?: string;
}

export interface AgentCapability {
  id?: string;
  label: string;
  category: string;
  proficiency: number;
}

export interface AgentConfig {
  max_context_tokens?: number;
  max_output_tokens?: number;
  supports_streaming?: boolean;
  supports_vision?: boolean;
  supports_tool_use?: boolean;
  supports_file_upload?: boolean;
  rate_limit_rpm?: number;
  rate_limit_tpm?: number;
  temperature?: number;
  system_prompt?: string;
  custom_prompt_prefix?: string;
  custom_parameters?: Record<string, unknown>;
  tools?: string[];
  skill_ids?: string[];
  mcp_server_ids?: string[];
  agentic_loop?: {
    enabled?: boolean;
    max_steps?: number;
    tool_policy?: string;
  };
  base_agent_id?: string;
  model_config_id?: string;
  model_id?: string;
  provider_id?: string;
}

export interface AgentConfigDraft {
  name: string;
  description: string;
  capabilities: AgentCapability[];
  system_prompt: string;
  tools: string[];
  skill_ids?: string[];
  mcp_server_ids?: string[];
  config: Record<string, unknown>;
  base_agent_id?: string;
  model_config_id?: string;
  capability_text?: string;
  temperature?: number;
}

export interface Agent {
  id: string;
  name: string;
  display_name?: string;
  type: string;
  version: string;
  avatar_url?: string;
  avatar_color?: string;
  capabilities: AgentCapability[];
  supported_content_types?: string[];
  description: string;
  status: "online" | "offline" | "maintenance" | "degraded";
  status_detail?: string;
  provider: string;
  is_official: boolean;
  response_latency_ms: number;
  config: AgentConfig;
  stats?: {
    total_conversations: number;
    total_messages: number;
    total_tokens_consumed: number;
    avg_response_time_ms: number;
    success_rate: number;
    last_active_at?: string;
  };
}

export interface UploadedFile {
  id: string;
  file_id?: string;
  filename: string;
  original_filename: string;
  content_type: string;
  size: number;
  purpose: string;
  parse_status: string;
  public_url?: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  scope: string;
  visibility: string;
  document_count: number;
  chunk_count: number;
  total_tokens: number;
  status: string;
}

export interface KnowledgeDocument {
  id: string;
  title: string;
  source_type: string;
  token_count: number;
  chunk_count: number;
  index_status: string;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  description: string;
  type: string;
  status: string;
  tags: string[];
  member_count: number;
  project_count: number;
  workflow?: Record<string, unknown>;
  config?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface ModelProvider {
  id: string;
  name: string;
  provider_type: string;
  base_url: string;
  default_model: string;
  supports_streaming: boolean;
  supports_embeddings: boolean;
  status: string;
  config?: Record<string, unknown>;
  models?: ModelConfig[];
  created_at?: string;
  updated_at?: string;
}

export interface ModelConfig {
  id: string;
  provider_id: string;
  provider_name?: string;
  name: string;
  model_id: string;
  purpose: string;
  context_window: number;
  max_output_tokens: number;
  temperature_default: number;
  config?: Record<string, unknown>;
  status: string;
  created_at?: string;
  updated_at?: string;
}

export interface McpServer {
  id: string;
  workspace_id?: string;
  created_by?: string;
  name: string;
  transport: "stdio" | "sse" | "httpStream" | "ws";
  url?: string;
  command?: string;
  args: string[];
  env?: Record<string, string>;
  headers?: Record<string, string>;
  enabled: boolean;
  health_status: "unknown" | "online" | "offline" | "disabled" | string;
  tools: Array<{ name: string; description?: string; enabled?: boolean }>;
  tool_filter: string[];
  timeout_ms: number;
  retry: number;
  last_checked_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface McpInvocation {
  id: string;
  server_id: string;
  workspace_id?: string;
  conversation_id?: string;
  tool_name: string;
  transport: string;
  arguments: Record<string, unknown>;
  status: "pending" | "running" | "succeeded" | "failed" | string;
  result: Record<string, unknown>;
  error_message?: string;
  duration_ms: number;
  created_at?: string;
  completed_at?: string;
}

export interface AuditLog {
  id: string;
  actor_id?: string;
  action: string;
  target_type: string;
  target_id?: string;
  ip_address?: string;
  risk_score: number;
  detail: Record<string, unknown>;
  created_at?: string;
}

export interface SecurityPermission {
  id: string;
  code: string;
  resource: string;
  action: string;
  description?: string;
}

export interface SecurityRole {
  id: string;
  code: string;
  name: string;
  description?: string;
  is_system: boolean;
  permissions: SecurityPermission[];
}

export interface SecurityUser {
  id: string;
  email: string;
  username: string;
  display_name: string;
  role: string;
  status: string;
  roles: string[];
  last_login_at?: string;
  created_at?: string;
}

export interface Skill {
  id: string;
  workspace_id?: string;
  name: string;
  description: string;
  category: string;
  scope: "workspace" | "platform" | "personal" | string;
  version: string;
  enabled: boolean;
  source: "manual" | "mcp" | "marketplace" | "import" | string;
  prompt_template?: string;
  tools: string[];
  mcp_server_id?: string;
  config?: Record<string, unknown>;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ToolDefinition {
  id: string;
  tool_id?: string;
  workspace_id?: string;
  name: string;
  display_name?: string;
  description: string;
  category: string;
  type: string;
  status: string;
  version: string;
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  permissions: string[];
  implementation?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
  tags: string[];
  config?: Record<string, unknown>;
  is_builtin?: boolean;
  created_by?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ToolInvokeResponse {
  tool: ToolDefinition;
  result: Record<string, unknown>;
}

export interface SandboxCommandResult {
  command: string;
  argv: string[];
  exit_code: number;
  stdout: string;
  stderr: string;
  duration_ms: number;
  created_at: string;
}

export interface SandboxSession {
  id: string;
  workspace_id?: string;
  project_id?: string;
  name: string;
  image: string;
  status: "ready" | "running" | "stopped" | "error" | string;
  resource_limits?: Record<string, unknown>;
  command_history: SandboxCommandResult[];
  last_command_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface RemoteConnection {
  id: string;
  workspace_id?: string;
  name: string;
  connection_type: "browser" | "ssh" | "vnc" | "rdp" | string;
  endpoint: string;
  status: "connected" | "disconnected" | "error" | string;
  capabilities: string[];
  session_state?: Record<string, unknown>;
  last_connected_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  type: string;
  status: string;
  tags: string[];
  file_count: number;
  current_version: number;
  created_at?: string;
  updated_at?: string;
}

export interface MessageAttachment {
  id?: string;
  file_id?: string;
  filename?: string;
  original_filename?: string;
  content_type?: string;
  size?: number;
  parse_status?: string;
  extracted_text?: string;
  public_url?: string;
  url?: string;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  role: MessageRole;
  kind: MessageKind;
  author: string;
  content: string;
  rawContent?: Record<string, unknown>;
  attachments?: MessageAttachment[];
  createdAt: string;
  streamState?: StreamState;
  quotedMessageId?: string;
}

export interface WorkspaceArtifact {
  id: string;
  conversationId: string;
  title: string;
  language: string;
  code: string;
  previousCode: string;
  previewUrl?: string;
  updatedAt: string;
}

export interface Deployment {
  id: string;
  status: "idle" | "building" | "ready" | "failed" | "deployed" | "deploying" | "pending";
  url?: string;
  commit: string;
  updatedAt: string;
}
