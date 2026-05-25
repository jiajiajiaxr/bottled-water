import { useMemo } from "react";
import {
  addEdge,
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge as FlowEdge,
  type Node as FlowNode,
  type NodeChange,
  applyNodeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Tag, Typography } from "antd";
import type { ConversationWorkflow, WorkflowNode, WorkflowRun } from "../../../../types";
import { WORKFLOW_NODE_TYPE_LABEL, workflowNodeType } from "../../../../lib/workflow";

const { Text } = Typography;

type WorkflowEdge = ConversationWorkflow["edges"][number];

function edgeSource(edge: WorkflowEdge): string {
  return Array.isArray(edge) ? String(edge[0]) : String(edge.from ?? edge.source ?? "");
}

function edgeTarget(edge: WorkflowEdge): string {
  return Array.isArray(edge) ? String(edge[1]) : String(edge.to ?? edge.target ?? "");
}

function edgeCondition(edge: WorkflowEdge): string | undefined {
  return Array.isArray(edge) ? undefined : edge.condition;
}

function toWorkflowEdge(edge: FlowEdge): WorkflowEdge {
  return edge.data?.condition
    ? { from: edge.source, to: edge.target, condition: String(edge.data.condition) }
    : [edge.source, edge.target];
}

function runtimeNode(workflowNode: WorkflowNode, latestRun?: WorkflowRun) {
  return latestRun?.node_states?.find((state) => state.id === workflowNode.id);
}

function runtimeEdge(edge: WorkflowEdge, latestRun?: WorkflowRun) {
  const from = edgeSource(edge);
  const to = edgeTarget(edge);
  return latestRun?.edge_states?.find((state) => state.from === from && state.to === to);
}

function statusColor(status?: string) {
  if (status === "completed" || status === "succeeded") return "#52c41a";
  if (status === "running" || status === "reviewing") return "#1677ff";
  if (status === "failed") return "#ff4d4f";
  if (status === "skipped") return "#8c8c8c";
  return "#d9d9d9";
}

function layoutNodes(workflow: ConversationWorkflow, latestRun?: WorkflowRun): FlowNode[] {
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
  const ready = nodes.filter((node) => (incoming.get(node.id) ?? 0) === 0).map((node) => node.id);
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
  return nodes.map((node, index) => {
    const config = node.config ?? {};
    const savedPosition = config.position as { x?: number; y?: number } | undefined;
    const currentLevel = level.get(node.id) ?? index;
    const order = levelCounts.get(currentLevel) ?? 0;
    levelCounts.set(currentLevel, order + 1);
    const state = runtimeNode(node, latestRun);
    const status = state?.status ?? node.status ?? "queued";
    const type = workflowNodeType(node);
    return {
      id: node.id,
      position: {
        x: Number(savedPosition?.x ?? currentLevel * 260 + 40),
        y: Number(savedPosition?.y ?? order * 140 + 80),
      },
      className: `xy-workflow-node xy-workflow-node-${status}`,
      data: {
        label: (
          <div className="xy-workflow-node-content">
            <div className="xy-workflow-node-header">
              <Text strong ellipsis>
                {node.title}
              </Text>
              <Tag color={statusColor(status)}>
                {WORKFLOW_NODE_TYPE_LABEL[type] ?? type}
              </Tag>
            </div>
            <Text type="secondary" ellipsis>
              {state?.message || node.meta || node.role}
            </Text>
            <div className="xy-workflow-node-footer">
              <span style={{ backgroundColor: statusColor(status) }} />
              <Text type={status === "failed" ? "danger" : "secondary"}>
                {status}
                {typeof state?.progress === "number" ? ` · ${state.progress}%` : ""}
              </Text>
            </div>
          </div>
        ),
      },
    };
  });
}

function layoutEdges(workflow: ConversationWorkflow, latestRun?: WorkflowRun): FlowEdge[] {
  return (workflow.edges ?? [])
    .map((edge) => {
      const from = edgeSource(edge);
      const to = edgeTarget(edge);
      if (!from || !to) return undefined;
      const state = runtimeEdge(edge, latestRun);
      const status = state?.status ?? (Array.isArray(edge) ? "waiting" : edge.status) ?? "waiting";
      const condition = edgeCondition(edge);
      return {
        id: `${from}-${to}-${condition ?? "edge"}`,
        source: from,
        target: to,
        label: condition,
        data: { condition },
        animated: status === "running" || status === "ready",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: statusColor(status), strokeWidth: status === "running" ? 2.5 : 1.5 },
      } satisfies FlowEdge;
    })
    .filter(Boolean) as FlowEdge[];
}

export function WorkflowCanvas({
  workflow,
  latestRun,
  onChange,
  onNodeClick,
}: {
  workflow: ConversationWorkflow;
  latestRun?: WorkflowRun;
  onChange: (workflow: ConversationWorkflow) => void;
  onNodeClick: (node: WorkflowNode) => void;
}) {
  const flowNodes = useMemo(() => layoutNodes(workflow, latestRun), [workflow, latestRun]);
  const flowEdges = useMemo(() => layoutEdges(workflow, latestRun), [workflow, latestRun]);
  const nodeById = useMemo(
    () => new Map((workflow.nodes ?? []).map((node) => [node.id, node])),
    [workflow.nodes],
  );

  const handleNodesChange = (changes: NodeChange[]) => {
    const nextFlowNodes = applyNodeChanges(changes, flowNodes);
    const positionById = new Map(nextFlowNodes.map((node) => [node.id, node.position]));
    onChange({
      ...workflow,
      nodes: workflow.nodes.map((node) => ({
        ...node,
        config: {
          ...(node.config ?? {}),
          position: positionById.get(node.id) ?? (node.config?.position as object | undefined),
        },
      })),
    });
  };

  const handleConnect = (connection: Connection) => {
    const nextEdges = addEdge(
      { ...connection, markerEnd: { type: MarkerType.ArrowClosed } },
      flowEdges,
    ).map(toWorkflowEdge);
    onChange({ ...workflow, edges: nextEdges });
  };

  return (
    <div className="xy-workflow-canvas">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        fitView
        nodesDraggable
        nodesConnectable
        onNodesChange={handleNodesChange}
        onConnect={handleConnect}
        onNodeClick={(_, node) => {
          const workflowNode = nodeById.get(node.id);
          if (workflowNode) onNodeClick(workflowNode);
        }}
      >
        <MiniMap pannable zoomable nodeStrokeWidth={3} />
        <Controls />
        <Background gap={20} />
      </ReactFlow>
    </div>
  );
}
