import { request } from "./client";
import { demoMcpServers } from "../mock";
import type { McpServer, McpInvocation } from "../types";

export async function mcpServers(workspaceId?: string): Promise<McpServer[]> {
  try {
    const query = workspaceId
      ? `?workspace_id=${encodeURIComponent(workspaceId)}`
      : "";
    const result = await request<{ items: McpServer[] }>(
      `/mcp-servers${query}`,
    );
    return result.items;
  } catch {
    return workspaceId
      ? demoMcpServers.filter((item) => item.workspace_id === workspaceId)
      : demoMcpServers;
  }
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
  try {
    return await request<McpServer>("/mcp-servers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `mcp-${Date.now()}`,
      workspace_id: payload.workspace_id,
      name: payload.name,
      transport: payload.transport as McpServer["transport"],
      url: payload.url,
      command: payload.command,
      args: payload.args ?? [],
      env: payload.env,
      headers: payload.headers,
      enabled: payload.enabled ?? true,
      health_status: "unknown",
      tools: [],
      tool_filter: payload.tool_filter ?? [],
      timeout_ms: payload.timeout_ms ?? 30000,
      retry: payload.retry ?? 1,
    };
  }
}

export async function importMcpServer(payload: {
  workspace_id?: string;
  source_type: "manifest_url" | "json" | string;
  source: string;
}): Promise<McpServer> {
  try {
    return await request<McpServer>("/mcp-servers/import", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    let parsed: Partial<McpServer> & { name?: string } = {};
    if (payload.source_type === "json") {
      try {
        const value = JSON.parse(payload.source);
        parsed = Array.isArray(value?.mcpServers)
          ? (value.mcpServers[0] ?? {})
          : value;
      } catch {
        parsed = {};
      }
    }
    const sourceLooksRemote = /^https?:\/\//i.test(payload.source.trim());
    return {
      id: `mcp-import-${Date.now()}`,
      workspace_id: payload.workspace_id,
      name:
        parsed.name ??
        (sourceLooksRemote ? "导入的远程 MCP" : "导入的 MCP 服务"),
      transport:
        (parsed.transport as McpServer["transport"]) ??
        (sourceLooksRemote ? "httpStream" : "stdio"),
      url:
        parsed.url ?? (sourceLooksRemote ? payload.source.trim() : undefined),
      command:
        parsed.command ??
        (sourceLooksRemote
          ? undefined
          : payload.source.trim().split(/\s+/)[0]),
      args: parsed.args ?? [],
      enabled: parsed.enabled ?? true,
      health_status: "unknown",
      tools: parsed.tools ?? [],
      tool_filter: parsed.tool_filter ?? [],
      timeout_ms: parsed.timeout_ms ?? 30000,
      retry: parsed.retry ?? 1,
    };
  }
}

export async function probeMcpServer(id: string): Promise<McpServer> {
  try {
    return await request<McpServer>(`/mcp-servers/${id}/probe`, {
      method: "POST",
    });
  } catch {
    const current =
      demoMcpServers.find((item) => item.id === id) ?? demoMcpServers[0];
    return {
      ...current,
      health_status: "online",
      last_checked_at: new Date().toISOString(),
    };
  }
}

export async function invokeMcpTool(
  serverId: string,
  toolName: string,
  argumentsValue: Record<string, unknown> = {},
  conversationId?: string,
): Promise<McpInvocation> {
  return await request<McpInvocation>(
    `/mcp-servers/${serverId}/tools/${encodeURIComponent(toolName)}/invoke`,
    {
      method: "POST",
      body: JSON.stringify({
        arguments: argumentsValue,
        conversation_id: conversationId,
      }),
    },
  );
}

export async function deleteMcpServer(
  serverId: string,
): Promise<{ id: string; deleted: boolean }> {
  return await request<{ id: string; deleted: boolean }>(
    `/mcp-servers/${serverId}`,
    { method: "DELETE" },
  );
}

export async function mcpInvocations(serverId?: string): Promise<McpInvocation[]> {
  const query = serverId ? `?server_id=${encodeURIComponent(serverId)}` : "";
  const result = await request<{ items: McpInvocation[] }>(
    `/mcp-invocations${query}`,
  );
  return result.items;
}
