import type { WorkflowNode } from "../../../types";
import { workflowNodeType } from "../../../lib/workflow";

export function canCreateWorkflowEdge({
  sourceId,
  targetId,
  nodeById,
  edgeKeys,
  locked,
}: {
  sourceId?: string | null;
  targetId?: string | null;
  nodeById: Map<string, WorkflowNode>;
  edgeKeys: Set<string>;
  locked: boolean;
}) {
  if (locked || !sourceId || !targetId) return false;
  if (sourceId === targetId) return false;
  const source = nodeById.get(sourceId);
  const target = nodeById.get(targetId);
  if (!source || !target) return false;
  if (workflowNodeType(source) === "end") return false;
  if (workflowNodeType(target) === "start") return false;
  return !edgeKeys.has(`${sourceId}->${targetId}`);
}

export function createWorkflowEdge(sourceId: string, targetId: string) {
  return {
    from: sourceId,
    to: targetId,
    sourceHandle: "output",
    targetHandle: "input",
    config: {
      source_handle: "output",
      target_handle: "input",
    },
  };
}
