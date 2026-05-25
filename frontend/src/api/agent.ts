import { request, requestWithTimeout } from "./client";
import { demoAgents } from "../mock";
import type { Agent, AgentCapability, AgentConfigDraft } from "../types";

export async function agents(params?: {
  search?: string;
  type?: string;
  status?: string;
}): Promise<Agent[]> {
  try {
    const query = new URLSearchParams();
    Object.entries(params ?? {}).forEach(
      ([key, value]) => value && query.set(key, value),
    );
    const result = await request<{ items: Agent[] } | Agent[]>(
      `/agents${query.toString() ? `?${query}` : ""}`,
    );
    return Array.isArray(result) ? result : result.items;
  } catch {
    return demoAgents;
  }
}

export async function createAgent(payload: AgentConfigDraft): Promise<Agent> {
  try {
    return await request<Agent>("/agents", {
      method: "POST",
      body: JSON.stringify({
        ...payload,
        type: "custom",
        provider: "custom",
        config: {
          ...(payload.config ?? {}),
          model_config_id: payload.model_config_id,
        },
      }),
    });
  } catch {
    return {
      id: `agent-${Date.now()}`,
      name: payload.name,
      display_name: payload.name,
      type: "custom",
      version: "1.0",
      avatar_color: "#6b7280",
      capabilities: payload.capabilities,
      description: payload.description,
      status: "online",
      provider: "custom",
      is_official: false,
      response_latency_ms: 1100,
      config: {
        ...payload.config,
        tools: payload.tools,
        system_prompt: payload.system_prompt,
        base_agent_id: payload.base_agent_id,
        model_config_id: payload.model_config_id,
      },
    };
  }
}

export async function updateAgent(
  agentId: string,
  payload: Partial<AgentConfigDraft> & {
    display_name?: string;
    status?: Agent["status"];
  },
): Promise<Agent> {
  try {
    return await request<Agent>(`/agents/${agentId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  } catch {
    const current =
      demoAgents.find((agent) => agent.id === agentId) ?? demoAgents[0];
    return {
      ...current,
      name: payload.name ?? current.name,
      display_name:
        payload.display_name ?? payload.name ?? current.display_name,
      description: payload.description ?? current.description,
      capabilities: payload.capabilities ?? current.capabilities,
      status: payload.status ?? current.status,
      config: {
        ...(current.config ?? {}),
        ...(payload.config ?? {}),
        ...(payload.system_prompt
          ? { system_prompt: payload.system_prompt }
          : {}),
        ...(payload.tools ? { tools: payload.tools } : {}),
      },
    };
  }
}

export async function deleteAgent(
  agentId: string,
): Promise<{ id: string; deleted: boolean }> {
  try {
    return await request<{ id: string; deleted: boolean }>(
      `/agents/${agentId}`,
      { method: "DELETE" },
    );
  } catch {
    return { id: agentId, deleted: true };
  }
}

export async function parseCapabilities(
  text: string,
): Promise<{ items: AgentCapability[]; system_prompt: string }> {
  try {
    return await request<{ items: AgentCapability[]; system_prompt: string }>(
      "/agents/parse-capabilities",
      {
        method: "POST",
        body: JSON.stringify({ text }),
      },
    );
  } catch {
    return {
      items: [
        { label: "任务分析", category: "通用", proficiency: 4 },
        { label: "结构化输出", category: "通用", proficiency: 4 },
      ],
      system_prompt: `你是${text}。请输出结构清晰、可执行、可验证的结果。`,
    };
  }
}

export async function generateAgentConfig(
  text: string,
  base_agent_id?: string,
  preferred_tools: string[] = [],
): Promise<AgentConfigDraft> {
  try {
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
  } catch {
    const dictionary: Array<[string, string, string]> = [
      ["React", "编码", "file.read"],
      ["前端", "编码", "file.write"],
      ["后端", "架构", "sandbox.run"],
      ["API", "架构", "api.test"],
      ["测试", "测试", "test.run"],
      ["知识库", "RAG", "file.summarize"],
      ["检索", "RAG", "file.summarize"],
      ["部署", "运维", "deploy.preview"],
      ["审查", "质量", "document.review"],
    ];
    const matched = dictionary.filter(([label]) =>
      text.toLowerCase().includes(label.toLowerCase()),
    );
    const fallbackCapabilities: Array<[string, string, string]> = [
      ["任务分析", "通用", "file.summarize"],
      ["结构化输出", "通用", "file.extract_text"],
    ];
    const capabilities = (
      matched.length ? matched : fallbackCapabilities
    ).map(([label, category]) => ({
      label,
      category,
      proficiency: 4,
    }));
    const tools = Array.from(
      new Set(matched.map(([, , tool]) => tool).filter(Boolean)),
    );
    const baseName = text
      .replace(/\s+/g, "")
      .replace(/[，。,.]/g, "")
      .slice(0, 14);
    return {
      name: baseName ? `${baseName} Agent` : "自定义 Agent",
      description: text.slice(0, 180) || "由 AI 生成配置的自定义 Agent。",
      capabilities,
      system_prompt: `你是${text || "一个自定义 Agent"}。请保持结构化、可验证、可执行，并在需要时调用已授权工具。`,
      tools: tools.length ? tools : ["file.extract_text"],
      config: { temperature: 0.7, generated_by: "frontend_fallback" },
      capability_text: text,
      temperature: 0.7,
    };
  }
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
  return await request<{ response: string }>(`/agents/${agentId}/test`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}
