import { get, post, del } from "./client";
import type { ToolDefinition, ToolInvokeResponse } from "@/types";

export async function tools(workspaceId?: string): Promise<ToolDefinition[]> {
  const query = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : "";
  const result = await get<{ items: ToolDefinition[] }>(
    `/tools${query}`,
  );
  return result.items;
}

export async function createTool(payload: {
  workspace_id?: string;
  name: string;
  display_name?: string;
  description: string;
  category: string;
  type?: string;
  permissions?: string[];
  implementation?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
  tags?: string[];
}): Promise<ToolDefinition> {
  return await post<ToolDefinition>("/tools", payload);
}

export async function generateTool(payload: {
  workspace_id?: string;
  name?: string;
  intent: string;
  requirements?: string;
  category?: string;
  allowed_permissions?: string[];
  tags?: string[];
}): Promise<ToolDefinition> {
  return await post<ToolDefinition>("/tools/generate", payload);
}

export async function invokeTool(
  toolId: string,
  argumentsValue: Record<string, unknown> = {},
  workspaceId?: string,
): Promise<ToolInvokeResponse> {
  return await post<ToolInvokeResponse>(
    `/tools/${encodeURIComponent(toolId)}/invoke`,
    {
      arguments: argumentsValue,
      workspace_id: workspaceId,
    },
  );
}

export async function deleteTool(toolId: string): Promise<{ id: string; deleted: boolean }> {
  return await del<{ id: string; deleted: boolean }>(
    `/tools/${encodeURIComponent(toolId)}`,
  );
}
