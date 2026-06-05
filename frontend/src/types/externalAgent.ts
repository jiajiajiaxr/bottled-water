export interface ExternalAgentProbe {
  provider: "codex" | "claude_code" | string;
  installed: boolean;
  command_path?: string | null;
  command_source?: string;
  reason?: string | null;
  setup_hint?: string;
  capabilities?: string[];
}

export interface ExternalAgentProbeResponse {
  providers: ExternalAgentProbe[];
  degraded: ExternalAgentProbe[];
}

export interface ExternalAgentRun {
  status: string;
  provider: string;
  run_id: string;
  workspace_id?: string | null;
  conversation_id?: string | null;
  agent_id?: string | null;
  cwd?: string;
  changed_files?: Array<Record<string, unknown>>;
  stdout_tail?: string;
  stderr_tail?: string;
  exit_code?: number | null;
  duration_ms?: number | null;
  error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}
