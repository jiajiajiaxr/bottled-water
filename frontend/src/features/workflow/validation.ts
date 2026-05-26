import type { ConversationWorkflow, WorkflowNode } from "../../types";
import { workflowNodeType } from "../../lib/workflow";
import { edgeId, edgeSource, edgeTarget } from "./utils";

export type WorkflowValidationIssue = {
  id: string;
  message: string;
  severity: "error";
  nodeId?: string;
  edgeId?: string;
};

const EXECUTABLE_NODE_TYPES = new Set([
  "agent",
  "tool",
  "skill",
  "mcp",
  "condition",
  "loop",
  "review",
  "artifact",
]);

function hasText(value: unknown): boolean {
  return typeof value === "string" && value.trim().length > 0;
}

function agentId(node: WorkflowNode): string {
  const config = node.config ?? {};
  return String(node.agent_id || config.agent_id || "").trim();
}

function edgePairs(workflow: ConversationWorkflow) {
  return (workflow.edges ?? []).map((edge) => ({
    edge,
    id: edgeId(edge),
    source: edgeSource(edge),
    target: edgeTarget(edge),
  }));
}

function reachableFromStart(workflow: ConversationWorkflow, startIds: string[]) {
  const outgoing = new Map<string, string[]>();
  const nodeIds = new Set((workflow.nodes ?? []).map((node) => node.id));
  edgePairs(workflow).forEach(({ source, target }) => {
    if (!nodeIds.has(source) || !nodeIds.has(target)) return;
    outgoing.set(source, [...(outgoing.get(source) ?? []), target]);
  });
  const reachable = new Set<string>();
  const queue = [...startIds];
  while (queue.length) {
    const current = queue.shift();
    if (!current || reachable.has(current)) continue;
    reachable.add(current);
    queue.push(...(outgoing.get(current) ?? []));
  }
  return reachable;
}

export function validateWorkflowDefinition(
  workflow?: ConversationWorkflow,
): WorkflowValidationIssue[] {
  const issues: WorkflowValidationIssue[] = [];
  if (!workflow) {
    return [
      {
        id: "workflow-missing",
        severity: "error",
        message: "当前会话没有工作流定义。",
      },
    ];
  }

  const nodes = workflow.nodes ?? [];
  const nodeIds = new Set(nodes.map((node) => node.id));
  const startNodes = nodes.filter((node) => workflowNodeType(node) === "start");
  const endNodes = nodes.filter((node) => workflowNodeType(node) === "end");
  const executableNodes = nodes.filter((node) =>
    EXECUTABLE_NODE_TYPES.has(workflowNodeType(node)),
  );

  if (!startNodes.length) {
    issues.push({
      id: "missing-start",
      severity: "error",
      message: "缺少 Start 节点。",
    });
  }
  if (!endNodes.length) {
    issues.push({
      id: "missing-end",
      severity: "error",
      message: "缺少 End 节点。",
    });
  }
  if (!executableNodes.length) {
    issues.push({
      id: "missing-executable-node",
      severity: "error",
      message: "至少需要一个可执行节点，例如 Agent、Tool、Skill 或 MCP。",
    });
  }

  edgePairs(workflow).forEach(({ id, source, target }) => {
    if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) {
      issues.push({
        id: `invalid-edge-${id}`,
        severity: "error",
        edgeId: id,
        message: `连线 ${source || "空"} -> ${target || "空"} 引用了不存在的节点。`,
      });
    }
  });

  if (startNodes.length) {
    const reachable = reachableFromStart(
      workflow,
      startNodes.map((node) => node.id),
    );
    nodes.forEach((node) => {
      if (workflowNodeType(node) === "start" || reachable.has(node.id)) return;
      issues.push({
        id: `unreachable-${node.id}`,
        severity: "error",
        nodeId: node.id,
        message: `节点「${node.title}」无法从 Start 到达。`,
      });
    });
    endNodes.forEach((node) => {
      if (reachable.has(node.id)) return;
      issues.push({
        id: `end-unreachable-${node.id}`,
        severity: "error",
        nodeId: node.id,
        message: `End 节点「${node.title}」无法被到达。`,
      });
    });
  }

  nodes.forEach((node) => {
    const type = workflowNodeType(node);
    const config = node.config ?? {};
    if ((type === "agent" || type === "review") && !agentId(node)) {
      issues.push({
        id: `missing-agent-${node.id}`,
        severity: "error",
        nodeId: node.id,
        message: `节点「${node.title}」必须选择 Agent。`,
      });
    }
    if (type === "tool" && !hasText(config.tool_name)) {
      issues.push({
        id: `missing-tool-${node.id}`,
        severity: "error",
        nodeId: node.id,
        message: `节点「${node.title}」必须选择工具名。`,
      });
    }
    if (type === "skill" && !hasText(config.skill_id)) {
      issues.push({
        id: `missing-skill-${node.id}`,
        severity: "error",
        nodeId: node.id,
        message: `节点「${node.title}」必须选择 Skill。`,
      });
    }
    if (
      type === "mcp" &&
      (!hasText(config.server_id) || !hasText(config.tool_name))
    ) {
      issues.push({
        id: `missing-mcp-${node.id}`,
        severity: "error",
        nodeId: node.id,
        message: `节点「${node.title}」必须选择 MCP 服务和工具。`,
      });
    }
  });

  return issues;
}

