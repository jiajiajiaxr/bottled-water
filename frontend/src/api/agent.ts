import { get, post, patch, del, requestWithTimeout } from "./client";
import type { Agent, AgentCapability, AgentConfigDraft } from "@/types";

export async function agents(params?: {
  search?: string;
  type?: string;
  status?: string;
}): Promise<Agent[]> {
  const query = new URLSearchParams();
  Object.entries(params ?? {}).forEach(
    ([key, value]) => value && query.set(key, value),
  );
  const result = await get<{ items: Agent[] } | Agent[]>(
    `/agents${query.toString() ? `?${query}` : ""}`,
  );
  return Array.isArray(result) ? result : result.items;
}

export async function createAgent(payload: AgentConfigDraft): Promise<Agent> {
  return await post<Agent>("/agents", {
    ...payload,
    type: "custom",
    provider: "custom",
    config: {
      ...(payload.config ?? {}),
      model_config_id: payload.model_config_id,
    },
  });
}

export async function updateAgent(
  agentId: string,
  payload: Partial<AgentConfigDraft> & {
    display_name?: string;
    status?: Agent["status"];
  },
): Promise<Agent> {
  return await patch<Agent>(`/agents/${agentId}`, payload);
}

export async function deleteAgent(
  agentId: string,
): Promise<{ id: string; deleted: boolean }> {
  return await del<{ id: string; deleted: boolean }>(`/agents/${agentId}`);
}

export async function parseCapabilities(
  text: string,
): Promise<{ items: AgentCapability[]; system_prompt: string }> {
  return await post<{ items: AgentCapability[]; system_prompt: string }>(
    "/agents/parse-capabilities",
    { text },
  );
}

export async function generateAgentConfig(
  text: string,
  base_agent_id?: string,
  preferred_tools: string[] = [],
): Promise<AgentConfigDraft> {
  return await requestWithTimeout<AgentConfigDraft>(
    "/agents/generate",
    {
      method: "POST",
      body: JSON.stringify({
        text,
        brief: text,
        base_agent_id,
        preferred_tools,
      }),
    },
    10000,
  );
}

export async function generateAgent(
  text: string,
  base_agent_id?: string,
  preferred_tools: string[] = [],
): Promise<AgentConfigDraft> {
  return generateAgentConfig(text, base_agent_id, preferred_tools);
}

export async function testAgent(
  agentId: string,
  message: string,
): Promise<{ response: string }> {
  return await post<{ response: string }>(`/agents/${agentId}/test`, { message });
}
