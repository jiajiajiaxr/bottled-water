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
