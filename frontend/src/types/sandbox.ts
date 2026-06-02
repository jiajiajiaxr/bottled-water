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
