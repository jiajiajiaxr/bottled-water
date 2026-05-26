import { request } from "./client";
import { demoMcpServers, demoSkills } from "@/mock";
import type { Skill } from "@/types";

function normalizeSkill(
  value: Skill & {
    status?: string;
    prompt?: string;
    content?: string;
    metadata?: Record<string, unknown>;
  },
): Skill {
  const rawTools = (value.tools ?? []) as unknown[];
  return {
    ...value,
    scope: value.scope ?? (value.workspace_id ? "workspace" : "platform"),
    enabled: value.enabled ?? value.status !== "disabled",
    prompt_template: value.prompt_template ?? value.prompt ?? value.content,
    tools: rawTools
      .map((tool) =>
        typeof tool === "string"
          ? tool
          : typeof tool === "object" && tool
            ? String((tool as { name?: unknown }).name ?? "")
            : "",
      )
      .filter(Boolean),
    mcp_server_id:
      value.mcp_server_id ??
      (value.config?.mcp as { server_id?: string } | undefined)?.server_id,
  };
}

export async function skills(workspaceId?: string): Promise<Skill[]> {
  try {
    const query = workspaceId
      ? `?workspace_id=${encodeURIComponent(workspaceId)}`
      : "";
    const result = await request<{ items: Skill[] } | Skill[]>(
      `/skills${query}`,
    );
    return (Array.isArray(result) ? result : result.items).map((skill) =>
      normalizeSkill(skill),
    );
  } catch {
    return workspaceId
      ? demoSkills.filter(
          (skill) =>
            !skill.workspace_id || skill.workspace_id === workspaceId,
        )
      : demoSkills;
  }
}

export async function createSkill(payload: {
  workspace_id?: string;
  name: string;
  description: string;
  category: string;
  scope: string;
  prompt_template?: string;
  tools: string[];
  enabled?: boolean;
  config?: Record<string, unknown>;
}): Promise<Skill> {
  try {
    const result = await request<Skill>("/skills", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: payload.workspace_id,
        name: payload.name,
        description: payload.description,
        category: payload.category,
        source: "manual",
        status: payload.enabled === false ? "disabled" : "active",
        content: payload.prompt_template ?? "",
        prompt: payload.prompt_template ?? "",
        tools: payload.tools.map((name) => ({ name, enabled: true })),
        tags: [payload.scope],
        config: payload.config ?? {},
      }),
    });
    return normalizeSkill(result);
  } catch {
    return {
      id: `skill-${Date.now()}`,
      workspace_id: payload.workspace_id,
      name: payload.name,
      description: payload.description,
      category: payload.category,
      scope: payload.scope,
      version: "1.0.0",
      enabled: payload.enabled ?? true,
      source: "manual",
      prompt_template: payload.prompt_template,
      tools: payload.tools,
      config: payload.config,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
  }
}

export async function importMcpAsSkill(payload: {
  workspace_id?: string;
  mcp_server_id: string;
  name?: string;
  category?: string;
}): Promise<Skill> {
  try {
    return normalizeSkill(
      await request<Skill>("/skills/import-mcp", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    );
  } catch {
    const server = demoMcpServers.find(
      (item) => item.id === payload.mcp_server_id,
    );
    return {
      id: `skill-mcp-${Date.now()}`,
      workspace_id: payload.workspace_id ?? server?.workspace_id,
      name: payload.name || `${server?.name ?? "MCP"} Skill`,
      description: `由 ${server?.name ?? payload.mcp_server_id} 导入的 MCP 工具能力。`,
      category: payload.category ?? "mcp",
      scope: "workspace",
      version: "1.0.0",
      enabled: true,
      source: "mcp",
      mcp_server_id: payload.mcp_server_id,
      tools:
        server?.tools?.map((tool) => tool.name) ?? server?.tool_filter ?? [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
  }
}

export async function generateSkill(payload: {
  workspace_id?: string;
  name?: string;
  intent: string;
  requirements?: string;
  category?: string;
  tags?: string[];
}): Promise<Skill> {
  return normalizeSkill(
    await request<Skill>("/skills/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  );
}

export async function testSkill(
  skillId: string,
  input: string,
): Promise<{
  status: string;
  response: string;
  model: string;
  usage?: Record<string, unknown>;
}> {
  return await request<{
    status: string;
    response: string;
    model: string;
    usage?: Record<string, unknown>;
  }>(`/skills/${skillId}/test`, {
    method: "POST",
    body: JSON.stringify({ input, message: input }),
  });
}

export async function deleteSkill(
  skillId: string,
): Promise<{ id: string; deleted: boolean }> {
  return await request<{ id: string; deleted: boolean }>(
    `/skills/${skillId}`,
    { method: "DELETE" },
  );
}
