import type { Agent, WorkflowNode } from "@/types";

export const WORKFLOW_NODE_TYPE_OPTIONS = [
  { label: "Agent", value: "agent" },
  { label: "Tool", value: "tool" },
  { label: "Condition", value: "condition" },
  { label: "Loop", value: "loop" },
  { label: "Review", value: "review" },
  { label: "Artifact", value: "artifact" },
];

export const WORKFLOW_NODE_TYPE_LABEL: Record<string, string> = {
  start: "Start",
  agent: "Agent",
  tool: "Tool",
  skill: "Skill",
  mcp: "MCP",
  condition: "Condition",
  loop: "Loop",
  review: "Review",
  artifact: "Artifact",
  end: "End",
};

const WORKFLOW_NODE_TYPES = new Set(Object.keys(WORKFLOW_NODE_TYPE_LABEL));

function normalizedNodeText(value: unknown) {
  return String(value ?? "").trim().toLowerCase();
}

export function workflowNodeType(node: WorkflowNode) {
  const id = normalizedNodeText(node.id);
  const role = normalizedNodeText(node.role);
  const type = normalizedNodeText(node.type);
  const title = normalizedNodeText(node.title);

  if (id === "start" || role === "start" || role === "input" || title === "start") {
    return "start";
  }
  if (id === "end" || role === "end" || title === "end") {
    return "end";
  }
  if (WORKFLOW_NODE_TYPES.has(type)) return type;
  if (role === "reviewer" || role === "review") return "review";
  if (role === "artifact" || role === "deploy" || role === "delivery") {
    return "artifact";
  }
  if (role === "tool") return "tool";
  if (role === "skill") return "skill";
  if (role === "mcp") return "mcp";
  if (role === "condition") return "condition";
  if (role === "loop") return "loop";
  return "agent";
}

export function createWorkflowNode(type: string, agent?: Agent): WorkflowNode {
  const id = `${type}-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`;
  const base: WorkflowNode = {
    id,
    title: WORKFLOW_NODE_TYPE_LABEL[type] ?? "Node",
    type,
    role: type === "review" ? "reviewer" : type,
    status: "ready",
    meta: "Manual step",
    config: {},
  };
  if (type === "agent" || type === "review") {
    base.agent_id = agent?.id;
    base.config = { agent_id: agent?.id };
    base.title = agent?.name ?? base.title;
  } else if (type === "tool") {
    base.config = { tool_name: "file.read" };
    base.meta = "Call an authorized tool";
  } else if (type === "condition") {
    base.config = {
      expression: "input.includes('review')",
      branches: ["true", "false"],
    };
    base.meta = "Route by expression";
  } else if (type === "loop") {
    base.config = { max_iterations: 3 };
    base.meta = "Repeat child steps";
  } else if (type === "artifact") {
    base.config = { artifact_type: "html" };
    base.meta = "Generate or export artifact";
  }
  return base;
}
