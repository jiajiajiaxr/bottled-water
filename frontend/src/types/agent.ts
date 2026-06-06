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
  capability_permissions_initialized?: boolean;
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
