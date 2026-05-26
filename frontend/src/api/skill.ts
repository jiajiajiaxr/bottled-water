import { get, post, del } from "./client";
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
  const query = workspaceId
    ? `?workspace_id=${encodeURIComponent(workspaceId)}`
    : "";
  const result = await get<{ items: Skill[] } | Skill[]>(
    `/skills${query}`,
  );
  return (Array.isArray(result) ? result : result.items).map((skill) =>
    normalizeSkill(skill),
  );
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
  const result = await post<Skill>("/skills", {
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
  });
  return normalizeSkill(result);
}

export async function importMcpAsSkill(payload: {
  workspace_id?: string;
  mcp_server_id: string;
  name?: string;
  category?: string;
}): Promise<Skill> {
  return normalizeSkill(
    await post<Skill>("/skills/import-mcp", payload),
  );
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
    await post<Skill>("/skills/generate", payload),
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
  return await post<{
    status: string;
    response: string;
    model: string;
    usage?: Record<string, unknown>;
  }>(`/skills/${skillId}/test`, { input, message: input });
}

export async function deleteSkill(
  skillId: string,
): Promise<{ id: string; deleted: boolean }> {
  return await del<{ id: string; deleted: boolean }>(
    `/skills/${skillId}`,
  );
}
