import { get, post, del } from "./client";
import type { McpServer, McpInvocation } from "@/types";

export async function mcpServers(workspaceId?: string): Promise<McpServer[]> {
  const query = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : "";
  const result = await get<{ items: McpServer[] }>(
    `/mcp-servers${query}`,
  );
  return result.items;
}

export async function createMcpServer(payload: {
  workspace_id?: string;
  name: string;
  transport: string;
  url?: string;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  headers?: Record<string, string>;
  enabled?: boolean;
  tool_filter?: string[];
  timeout_ms?: number;
  retry?: number;
}): Promise<McpServer> {
  return await post<McpServer>("/mcp-servers", payload);
}

export async function importMcpServer(payload: {
  workspace_id?: string;
  source_type: "manifest_url" | "json" | string;
  source: string;
}): Promise<McpServer> {
  return await post<McpServer>("/mcp-servers/import", payload);
}

export async function probeMcpServer(id: string): Promise<McpServer> {
  return await post<McpServer>(`/mcp-servers/${id}/probe`, {});
}

export async function invokeMcpTool(
  serverId: string,
  toolName: string,
  argumentsValue: Record<string, unknown> = {},
  conversationId?: string,
): Promise<McpInvocation> {
  return await post<McpInvocation>(
    `/mcp-servers/${serverId}/tools/${encodeURIComponent(toolName)}/invoke`,
    {
      arguments: argumentsValue,
      conversation_id: conversationId,
    },
  );
}

export async function deleteMcpServer(
  serverId: string,
): Promise<{ id: string; deleted: boolean }> {
  return await del<{ id: string; deleted: boolean }>(
    `/mcp-servers/${serverId}`,
  );
}

export async function mcpInvocations(serverId?: string): Promise<McpInvocation[]> {
  const query = serverId ? `?server_id=${encodeURIComponent(serverId)}` : "";
  const result = await get<{ items: McpInvocation[] }>(
    `/mcp-invocations${query}`,
  );
  return result.items;
}
