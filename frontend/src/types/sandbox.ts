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

export interface TerminalSnapshot {
  status?: "succeeded" | "timeout" | "failed" | string;
  capability_level?: "interactive" | string;
  session_id: string;
  sandbox_id?: string;
  session_status: "running" | "completed" | "failed" | "timeout" | "cancelled" | string;
  transport?: "pty" | "pipes" | string;
  command: string;
  argv: string[];
  cwd: string;
  stdout_tail: string;
  stderr_tail: string;
  exit_code?: number | null;
  duration_ms: number;
  files?: Array<{ path: string; size: number; updated_at?: number }>;
  matched?: boolean;
  matched_pattern?: string | null;
  waited_ms?: number;
  input_events?: Array<{ at: string; text: string }>;
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
