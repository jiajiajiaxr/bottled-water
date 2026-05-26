import type { Agent, WorkflowNode } from "../types";

export const WORKFLOW_NODE_TYPE_OPTIONS = [
  { label: "Agent", value: "agent" },
  { label: "Tool", value: "tool" },
  { label: "Skill", value: "skill" },
  { label: "MCP", value: "mcp" },
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

export function workflowNodeType(node: WorkflowNode) {
  return (
    node.type ||
    (node.role === "reviewer"
      ? "review"
      : node.role === "artifact"
        ? "artifact"
        : node.role === "input"
          ? "start"
          : "agent")
  );
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
    data: {},
    config: {},
  };
  if (type === "agent" || type === "review") {
    base.agent_id = agent?.id;
    base.config = { agent_id: agent?.id };
    base.title = agent?.name ?? base.title;
  } else if (type === "tool") {
    base.config = { tool_name: "file.read" };
    base.meta = "Call an authorized tool";
  } else if (type === "skill") {
    base.config = { skill_id: "" };
    base.meta = "Run a workspace Skill";
  } else if (type === "mcp") {
    base.config = { server_id: "", tool_name: "" };
    base.meta = "Call an MCP server tool";
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
