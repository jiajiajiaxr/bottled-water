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
