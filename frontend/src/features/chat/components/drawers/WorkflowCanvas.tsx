import { useMemo } from "react";
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge as FlowEdge,
  type EdgeChange,
  type Node as FlowNode,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Spin, Tag, Typography } from "antd";
import type {
  ConversationWorkflow,
  WorkflowNode,
  WorkflowRun,
} from "../../../../types";
import {
  WORKFLOW_NODE_TYPE_LABEL,
  workflowNodeType,
} from "../../../../lib/workflow";
import {
  layoutWorkflowPositions,
  workflowNodeSavedPosition,
} from "../../../../lib/workflowLayout";

const { Text } = Typography;

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

function edgeCondition(edge: WorkflowEdge): string | undefined {
  return Array.isArray(edge) ? undefined : edge.condition;
}

function toWorkflowEdge(edge: FlowEdge): WorkflowEdge {
  return edge.data?.condition
    ? {
        from: edge.source,
        to: edge.target,
        condition: String(edge.data.condition),
      }
    : [edge.source, edge.target];
}

function runtimeNode(workflowNode: WorkflowNode, latestRun?: WorkflowRun) {
  return latestRun?.node_states?.find((state) => state.id === workflowNode.id);
}

function runtimeEdge(edge: WorkflowEdge, latestRun?: WorkflowRun) {
  const from = edgeSource(edge);
  const to = edgeTarget(edge);
  return latestRun?.edge_states?.find(
    (state) => state.from === from && state.to === to,
  );
}

function statusColor(status?: string) {
  if (status === "completed" || status === "succeeded") return "#52c41a";
  if (status === "running" || status === "reviewing") return "#1677ff";
  if (status === "failed") return "#ff4d4f";
  if (status === "skipped") return "#8c8c8c";
  return "#d9d9d9";
}

function layoutNodes(
  workflow: ConversationWorkflow,
  latestRun?: WorkflowRun,
): FlowNode[] {
  const positionedWorkflow = layoutWorkflowPositions(workflow);
  return (positionedWorkflow.nodes ?? []).map((node) => {
    const state = runtimeNode(node, latestRun);
    const status = state?.status ?? node.status ?? "queued";
    const type = workflowNodeType(node);
    return {
      id: node.id,
      position: workflowNodeSavedPosition(node) ?? { x: 48, y: 64 },
      className: `xy-workflow-node xy-workflow-node-${status}`,
      data: {
        label: (
          <div className="xy-workflow-node-content">
            <div className="xy-workflow-node-header">
              <Text strong className="xy-workflow-node-title" ellipsis>
                {node.title}
              </Text>
              <Tag className="xy-workflow-node-type" color={statusColor(status)}>
                {WORKFLOW_NODE_TYPE_LABEL[type] ?? type}
              </Tag>
            </div>
            <Text className="xy-workflow-node-meta" type="secondary" ellipsis>
              {state?.message || node.meta || node.role}
            </Text>
            <div className="xy-workflow-node-footer">
              <span style={{ backgroundColor: statusColor(status) }} />
              <Text
                className="xy-workflow-node-status"
                type={status === "failed" ? "danger" : "secondary"}
                ellipsis
              >
                {status}
                {typeof state?.progress === "number"
                  ? ` · ${state.progress}%`
                  : ""}
              </Text>
            </div>
          </div>
        ),
      },
    };
  });
}

function layoutEdges(
  workflow: ConversationWorkflow,
  latestRun?: WorkflowRun,
): FlowEdge[] {
  return (workflow.edges ?? [])
    .map((edge) => {
      const from = edgeSource(edge);
      const to = edgeTarget(edge);
      if (!from || !to) return undefined;
      const state = runtimeEdge(edge, latestRun);
      const status =
        state?.status ?? (Array.isArray(edge) ? "waiting" : edge.status) ?? "waiting";
      const condition = edgeCondition(edge);
      return {
        id: `${from}-${to}-${condition ?? "edge"}`,
        source: from,
        target: to,
        label: condition,
        data: { condition },
        animated: status === "running" || status === "ready",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: {
          stroke: statusColor(status),
          strokeWidth: status === "running" ? 2.5 : 1.5,
        },
      } satisfies FlowEdge;
    })
    .filter(Boolean) as FlowEdge[];
}

export function WorkflowCanvas({
  workflow,
  latestRun,
  locked = false,
  overlayText,
  onChange,
  onNodeClick,
}: {
  workflow: ConversationWorkflow;
  latestRun?: WorkflowRun;
  locked?: boolean;
  overlayText?: string;
  onChange: (workflow: ConversationWorkflow) => void;
  onNodeClick: (node: WorkflowNode) => void;
}) {
  const flowNodes = useMemo(
    () => layoutNodes(workflow, latestRun),
    [workflow, latestRun],
  );
  const flowEdges = useMemo(
    () => layoutEdges(workflow, latestRun),
    [workflow, latestRun],
  );
  const nodeById = useMemo(
    () => new Map((workflow.nodes ?? []).map((node) => [node.id, node])),
    [workflow.nodes],
  );

  const handleNodesChange = (changes: NodeChange[]) => {
    if (locked) return;
    const nextFlowNodes = applyNodeChanges(changes, flowNodes);
    const positionById = new Map(
      nextFlowNodes.map((node) => [node.id, node.position]),
    );
    onChange({
      ...workflow,
      nodes: workflow.nodes.map((node) => ({
        ...node,
        position: positionById.get(node.id) ?? node.position,
      })),
    });
  };

  const handleEdgesChange = (changes: EdgeChange[]) => {
    if (locked) return;
    onChange({
      ...workflow,
      edges: applyEdgeChanges(changes, flowEdges).map(toWorkflowEdge),
    });
  };

  const handleConnect = (connection: Connection) => {
    if (locked) return;
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
        nodesDraggable={!locked}
        nodesConnectable={!locked}
        elementsSelectable={!locked}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onNodeClick={(_, node) => {
          if (locked) return;
          const workflowNode = nodeById.get(node.id);
          if (workflowNode) onNodeClick(workflowNode);
        }}
      >
        <MiniMap pannable zoomable nodeStrokeWidth={3} />
        <Controls />
        <Background gap={20} />
      </ReactFlow>
      {overlayText && (
        <div className="xy-workflow-overlay">
          <Spin />
          <Text strong>{overlayText}</Text>
        </div>
      )}
    </div>
  );
}
