import {
  MarkerType,
  type Edge as FlowEdge,
  type Node as FlowNode,
} from "@xyflow/react";
import type { MouseEvent, PointerEvent } from "react";
import type {
  ConversationWorkflow,
  WorkflowNode,
  WorkflowRun,
} from "../../../types";
import { workflowNodeType } from "../../../lib/workflow";
import {
  layoutWorkflowPositions,
  workflowNodeSavedPosition,
} from "../../../lib/workflowLayout";
import type { WorkflowValidationIssue } from "../validation";
import {
  edgeCondition,
  edgeSource,
  edgeSourceHandle,
  edgeTarget,
  edgeTargetHandle,
} from "../utils";
import type { WorkflowFlowEdgeData } from "./WorkflowFlowEdge";
import type { WorkflowFlowNodeData } from "./WorkflowFlowNode";

type WorkflowEdge = ConversationWorkflow["edges"][number];

function edgeRuntime(edge: WorkflowEdge, latestRun?: WorkflowRun) {
  const from = edgeSource(edge);
  const to = edgeTarget(edge);
  return latestRun?.edge_states?.find(
    (state) => state.from === from && state.to === to,
  );
}

function nodeRuntime(workflowNode: WorkflowNode, latestRun?: WorkflowRun) {
  return latestRun?.node_states?.find((state) => state.id === workflowNode.id);
}

function normalizeStatus(status?: string) {
  if (!status || status === "ready") return "queued";
  if (status === "completed") return "succeeded";
  return status;
}

function statusColor(status?: string) {
  const value = normalizeStatus(status);
  if (value === "succeeded") return "#52c41a";
  if (value === "running" || value === "reviewing") return "#1677ff";
  if (value === "failed") return "#ff4d4f";
  if (value === "skipped") return "#8c8c8c";
  return "#d9d9d9";
}

function workflowEdgeId(edge: WorkflowEdge): string {
  return `${edgeSource(edge)}-${edgeTarget(edge)}-${edgeCondition(edge) ?? "edge"}`;
}

export function toWorkflowEdge(edge: FlowEdge): WorkflowEdge {
  const config = {
    source_handle: edge.sourceHandle ?? "output",
    target_handle: edge.targetHandle ?? "input",
  };
  return {
    from: edge.source,
    to: edge.target,
    sourceHandle: edge.sourceHandle ?? "output",
    targetHandle: edge.targetHandle ?? "input",
    config,
    ...(edge.data?.condition
      ? { condition: String(edge.data.condition) }
      : {}),
  };
}

export function layoutWorkflowCanvasNodes(
  workflow: ConversationWorkflow,
  latestRun?: WorkflowRun,
  selectedNodeIds: string[] = [],
  invalidNodeIds: Set<string> = new Set(),
  warningNodeIds: Set<string> = new Set(),
  onNodeClick?: (node: WorkflowNode) => void,
  connection?: {
    connectingSourceId?: string;
    connectingTargetId?: string;
    canConnectToNode?: (nodeId: string) => boolean;
    onStartConnection?: (
      nodeId: string,
      event: PointerEvent<HTMLElement>,
    ) => void;
    onStartConnectionFromMouse?: (
      nodeId: string,
      event: MouseEvent<HTMLElement>,
    ) => void;
    onArmConnection?: (
      nodeId: string,
      event: MouseEvent<HTMLElement>,
    ) => void;
    onCompleteConnection?: (
      nodeId: string,
      event: MouseEvent<HTMLElement> | PointerEvent<HTMLElement>,
    ) => void;
  },
): FlowNode<WorkflowFlowNodeData>[] {
  const positionedWorkflow = layoutWorkflowPositions(workflow);
  return (positionedWorkflow.nodes ?? []).map((node) => {
    const state = nodeRuntime(node, latestRun);
    const status = normalizeStatus(state?.status ?? node.status);
    const type = workflowNodeType(node);
    const nodeId = String(node.id);
    return {
      id: nodeId,
      type: "workflow",
      position: workflowNodeSavedPosition(node) ?? { x: 48, y: 64 },
      style: { width: 248, height: 116 },
      measured: { width: 248, height: 116 },
      selected: selectedNodeIds.includes(nodeId),
      selectable: true,
      draggable: true,
      focusable: true,
      className: [
        "xy-workflow-node",
        `xy-workflow-node-${status}`,
        invalidNodeIds.has(nodeId) ? "xy-workflow-node-invalid" : "",
        warningNodeIds.has(nodeId) ? "xy-workflow-node-warning" : "",
      ]
        .filter(Boolean)
        .join(" "),
      data: {
        workflowNode: node,
        nodeType: type,
        status,
        statusColor: statusColor(status),
        message: state?.message || node.meta || node.role || "-",
        progress: state?.progress,
        onNodeClick,
        canReceiveConnection: connection?.canConnectToNode?.(nodeId),
        connectingSourceId: connection?.connectingSourceId,
        connectingTargetId: connection?.connectingTargetId,
        onStartConnection: connection?.onStartConnection,
        onStartConnectionFromMouse: connection?.onStartConnectionFromMouse,
        onArmConnection: connection?.onArmConnection,
        onCompleteConnection: connection?.onCompleteConnection,
      },
    };
  });
}

export function layoutWorkflowCanvasEdges(
  workflow: ConversationWorkflow,
  latestRun?: WorkflowRun,
  selectedEdgeIds: string[] = [],
  invalidEdgeIssues: Map<string, WorkflowValidationIssue> = new Map(),
  actions: {
    onSelect?: (edgeId: string) => void;
  } = {},
): FlowEdge<WorkflowFlowEdgeData>[] {
  return (workflow.edges ?? [])
    .map((edge) => {
      const from = edgeSource(edge);
      const to = edgeTarget(edge);
      if (!from || !to) return undefined;
      const state = edgeRuntime(edge, latestRun);
      const status = normalizeStatus(
        state?.status ?? (Array.isArray(edge) ? "queued" : edge.status),
      );
      const condition = edgeCondition(edge);
      const id = workflowEdgeId(edge);
      const issue = invalidEdgeIssues.get(id);
      const selected = selectedEdgeIds.includes(id);
      return {
        id,
        type: "workflowEdge",
        source: from,
        target: to,
        sourceHandle: edgeSourceHandle(edge),
        targetHandle: edgeTargetHandle(edge),
        interactionWidth: 34,
        label: issue ? condition || "连线错误" : condition,
        selected,
        data: {
          condition,
          issueLabel: issue?.message,
          selected,
          statusColor: statusColor(status),
          onSelect: actions.onSelect,
        },
        className: [
          issue ? "xy-workflow-edge-invalid" : "",
          selected ? "xy-workflow-edge-selected" : "",
        ]
          .filter(Boolean)
          .join(" "),
        animated: status === "running",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: {
          stroke: selected ? "#1677ff" : issue ? "#ff4d4f" : statusColor(status),
          strokeWidth: selected || issue || status === "running" ? 2.8 : 1.6,
        },
      } satisfies FlowEdge<WorkflowFlowEdgeData>;
    })
    .filter(Boolean) as FlowEdge<WorkflowFlowEdgeData>[];
}
