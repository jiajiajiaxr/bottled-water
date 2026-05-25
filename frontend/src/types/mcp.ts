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
