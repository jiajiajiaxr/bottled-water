import type { ConversationWorkflow } from "../../types";

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

export function workflowSettings(workflow?: ConversationWorkflow) {
  return workflow?.settings ?? {};
}

export function statusTagColor(status?: string) {
  if (status === "completed" || status === "succeeded") return "success";
  if (status === "failed") return "error";
  if (status === "running" || status === "queued") return "processing";
  return "default";
}
