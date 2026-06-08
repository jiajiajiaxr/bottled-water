import { workflowNodeType } from "../../lib/workflow";
import type { Agent, ConversationWorkflow, Participant, WorkflowNode } from "../../types";

export type WorkflowEdge = ConversationWorkflow["edges"][number];

export function edgeSource(edge: WorkflowEdge) {
  return Array.isArray(edge)
    ? String(edge[0])
    : String(edge.from ?? edge.source ?? "");
}

export function edgeTarget(edge: WorkflowEdge) {
  return Array.isArray(edge)
    ? String(edge[1])
    : String(edge.to ?? edge.target ?? "");
}

export function edgeCondition(edge: WorkflowEdge) {
  return Array.isArray(edge) ? undefined : edge.condition;
}

export function edgeSourceHandle(edge: WorkflowEdge) {
  if (Array.isArray(edge)) return "output";
  const config = edge.config ?? {};
  return String(edge.sourceHandle ?? config.source_handle ?? config.sourceHandle ?? "output");
}

export function edgeTargetHandle(edge: WorkflowEdge) {
  if (Array.isArray(edge)) return "input";
  const config = edge.config ?? {};
  return String(edge.targetHandle ?? config.target_handle ?? config.targetHandle ?? "input");
}

export function edgeId(edge: WorkflowEdge) {
  return `${edgeSource(edge)}-${edgeTarget(edge)}-${edgeCondition(edge) ?? "edge"}`;
}

export function textFromConfigValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export function configValueFromText(value?: string) {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return undefined;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return trimmed;
  }
}

export function workflowSettings(workflow?: ConversationWorkflow): Record<string, unknown> & {
  enabled: boolean;
} {
  return { enabled: false, ...(workflow?.settings ?? {}) };
}

export function workflowNodeLabel(node: WorkflowNode) {
  const title = typeof node.title === "string" ? node.title.trim() : "";
  if (title && title.toLowerCase() !== "undefined") return title;
  return node.id || workflowNodeType(node);
}

export function normalizeWorkflowForRun(
  workflow: ConversationWorkflow,
): ConversationWorkflow {
  return {
    ...workflow,
    nodes: (workflow.nodes ?? []).map((node) => {
      const type = workflowNodeType(node);
      const config = node.config ?? {};
      const agentId =
        type === "agent" || type === "review"
          ? String(node.agent_id || config.agent_id || "").trim()
          : "";
      return {
        ...node,
        title: workflowNodeLabel(node),
        type,
        role: type,
        ...(agentId ? { agent_id: agentId } : {}),
        config: agentId ? { ...config, agent_id: agentId } : config,
      };
    }),
  };
}

function textParts(...values: unknown[]) {
  return values
    .flatMap((value) => {
      if (Array.isArray(value)) return value;
      return [value];
    })
    .map((value) => String(value ?? "").trim().toLowerCase())
    .filter(Boolean);
}

function activeParticipantAgents(
  participants: Participant[] = [],
  agents: Agent[] = [],
): Agent[] {
  const activeIds = new Set(
    participants
      .filter((item) => item.participant_type === "agent" && !item.left_at)
      .map((item) => item.agent_id)
      .filter((id): id is string => Boolean(id)),
  );
  const byId = new Map(agents.map((agent) => [agent.id, agent]));
  return Array.from(activeIds)
    .map((id) => byId.get(id))
    .filter((agent): agent is Agent => Boolean(agent));
}

function agentSearchText(agent: Agent) {
  const capabilities = Array.isArray(agent.capabilities)
    ? agent.capabilities.flatMap((item) =>
        item && typeof item === "object"
          ? [
              item.label,
              (item as unknown as Record<string, unknown>).name,
              item.category,
            ]
          : [item],
      )
    : [];
  return textParts(
    agent.id,
    agent.name,
    agent.type,
    agent.description,
    capabilities,
  ).join(" ");
}

function workflowNodeSearchText(node: WorkflowNode) {
  const config = node.config ?? {};
  const data = node.data ?? {};
  return textParts(
    node.id,
    node.title,
    node.role,
    node.type,
    node.meta,
    node.agent_id,
    config.agent_id,
    config.agentId,
    config.assigned_agent_id,
    config.agent_name,
    config.agent_type,
    data.title,
    data.label,
    data.agent_name,
    data.agent_type,
  ).join(" ");
}

function resolveWorkflowNodeAgentId(
  node: WorkflowNode,
  candidates: Agent[],
  usedAgentIds: Set<string>,
): string | undefined {
  const config = node.config ?? {};
  const hints = textParts(
    node.agent_id,
    config.agent_id,
    config.agentId,
    config.assigned_agent_id,
  );
  const byId = new Map(candidates.map((agent) => [agent.id, agent]));
  for (const hint of hints) {
    if (byId.has(hint)) return hint;
  }

  const nodeText = workflowNodeSearchText(node);
  const scored = candidates.map((agent, index) => {
    const agentText = agentSearchText(agent);
    let score = 0;
    if (workflowNodeType(node) === "review" && agent.type === "reviewer") score += 8;
    if (workflowNodeType(node) === "agent" && agent.type !== "reviewer") score += 2;
    if (agent.name && nodeText.includes(agent.name.toLowerCase())) score += 12;
    if (agent.type && nodeText.includes(agent.type.toLowerCase())) score += 6;
    for (const hint of hints) {
      if (hint && (agentText.includes(hint) || agent.id.toLowerCase().startsWith(hint))) {
        score += 10;
      }
    }
    for (const token of nodeText.split(/\s+/)) {
      if (token.length >= 3 && agentText.includes(token)) score += 1;
    }
    if (usedAgentIds.has(agent.id)) score -= 3;
    return { agent, index, score };
  });
  scored.sort((left, right) => right.score - left.score || left.index - right.index);
  if (scored[0]?.score > 0) return scored[0].agent.id;

  const preferred = candidates.find(
    (agent) =>
      !usedAgentIds.has(agent.id) &&
      (workflowNodeType(node) === "review"
        ? agent.type === "reviewer"
        : agent.type !== "reviewer"),
  );
  return preferred?.id ?? candidates.find((agent) => !usedAgentIds.has(agent.id))?.id ?? candidates[0]?.id;
}

export function normalizeWorkflowAgentBindings(
  workflow: ConversationWorkflow,
  participants: Participant[] = [],
  agents: Agent[] = [],
): ConversationWorkflow {
  const candidates = activeParticipantAgents(participants, agents);
  if (!candidates.length) return workflow;

  const activeIds = new Set(candidates.map((agent) => agent.id));
  const usedAgentIds = new Set<string>();
  return {
    ...workflow,
    nodes: (workflow.nodes ?? []).map((node) => {
      const type = workflowNodeType(node);
      if (type !== "agent" && type !== "review") return node;
      const config = node.config ?? {};
      const current = String(node.agent_id || config.agent_id || "").trim();
      const agentId = activeIds.has(current)
        ? current
        : resolveWorkflowNodeAgentId(node, candidates, usedAgentIds);
      if (!agentId) return node;
      usedAgentIds.add(agentId);
      return {
        ...node,
        agent_id: agentId,
        config: {
          ...config,
          agent_id: agentId,
        },
      };
    }),
  };
}

export function statusTagColor(status?: string) {
  if (status === "completed" || status === "succeeded") return "success";
  if (status === "failed") return "error";
  if (status === "running" || status === "queued") return "processing";
  return "default";
}
