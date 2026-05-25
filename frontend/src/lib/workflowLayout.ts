import type { ConversationWorkflow, WorkflowNode } from "../types";

type WorkflowEdge = ConversationWorkflow["edges"][number];

function edgeSource(edge: WorkflowEdge): string {
  return Array.isArray(edge)
    ? String(edge[0])
    : String(edge.from ?? edge.source ?? "");
}

function edgeTarget(edge: WorkflowEdge): string {
  return Array.isArray(edge)
    ? String(edge[1])
    : String(edge.to ?? edge.target ?? "");
}

function computeAutoPositions(workflow: ConversationWorkflow) {
  const nodes = workflow.nodes ?? [];
  const incoming = new Map<string, number>();
  const outgoing = new Map<string, string[]>();
  nodes.forEach((node) => {
    incoming.set(node.id, 0);
    outgoing.set(node.id, []);
  });
  (workflow.edges ?? []).forEach((edge) => {
    const from = edgeSource(edge);
    const to = edgeTarget(edge);
    if (!incoming.has(from) || !incoming.has(to)) return;
    incoming.set(to, (incoming.get(to) ?? 0) + 1);
    outgoing.set(from, [...(outgoing.get(from) ?? []), to]);
  });

  const level = new Map<string, number>();
  const ready = nodes
    .filter((node) => (incoming.get(node.id) ?? 0) === 0)
    .map((node) => node.id);
  ready.forEach((id) => level.set(id, 0));
  while (ready.length) {
    const id = ready.shift()!;
    const nextLevel = (level.get(id) ?? 0) + 1;
    (outgoing.get(id) ?? []).forEach((target) => {
      incoming.set(target, (incoming.get(target) ?? 1) - 1);
      if ((incoming.get(target) ?? 0) <= 0) {
        level.set(target, Math.max(level.get(target) ?? 0, nextLevel));
        ready.push(target);
      }
    });
  }

  const levelCounts = new Map<number, number>();
  const positions = new Map<string, { x: number; y: number }>();
  nodes.forEach((node, index) => {
    const currentLevel = level.get(node.id) ?? index;
    const order = levelCounts.get(currentLevel) ?? 0;
    levelCounts.set(currentLevel, order + 1);
    positions.set(node.id, {
      x: currentLevel * 280 + 48,
      y: order * 150 + 64,
    });
  });
  return positions;
}

export function workflowNodeSavedPosition(node: WorkflowNode) {
  const legacyPosition = node.config?.position as
    | { x?: number; y?: number }
    | undefined;
  const position = node.position ?? legacyPosition;
  if (typeof position?.x !== "number" || typeof position?.y !== "number") {
    return undefined;
  }
  return { x: position.x, y: position.y };
}

export function layoutWorkflowPositions(
  workflow: ConversationWorkflow,
): ConversationWorkflow {
  const positions = computeAutoPositions(workflow);
  return {
    ...workflow,
    nodes: (workflow.nodes ?? []).map((node) => {
      const savedPosition = workflowNodeSavedPosition(node);
      return {
        ...node,
        position: savedPosition ?? positions.get(node.id),
      };
    }),
  };
}
