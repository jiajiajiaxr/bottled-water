import { useCallback, useEffect, useMemo, useRef, type DragEvent } from "react";
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  ConnectionMode,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  SelectionMode,
  type Connection,
  type Edge as FlowEdge,
  type EdgeChange,
  type Node as FlowNode,
  type NodeChange,
  type ReactFlowInstance,
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
import type { WorkflowValidationIssue } from "../../../workflow/validation";

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

function edgeId(edge: WorkflowEdge): string {
  const from = edgeSource(edge);
  const to = edgeTarget(edge);
  return `${from}-${to}-${edgeCondition(edge) ?? "edge"}`;
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

function layoutNodes(
  workflow: ConversationWorkflow,
  latestRun?: WorkflowRun,
  selectedNodeIds: string[] = [],
  invalidNodeIds: Set<string> = new Set(),
  onNodeClick?: (node: WorkflowNode) => void,
): FlowNode[] {
  const positionedWorkflow = layoutWorkflowPositions(workflow);
  return (positionedWorkflow.nodes ?? []).map((node) => {
    const state = runtimeNode(node, latestRun);
    const status = normalizeStatus(state?.status ?? node.status);
    const type = workflowNodeType(node);
    return {
      id: node.id,
      position: workflowNodeSavedPosition(node) ?? { x: 48, y: 64 },
      selected: selectedNodeIds.includes(node.id),
      selectable: true,
      draggable: true,
      focusable: true,
      className: [
        "xy-workflow-node",
        `xy-workflow-node-${status}`,
        invalidNodeIds.has(node.id) ? "xy-workflow-node-invalid" : "",
      ]
        .filter(Boolean)
        .join(" "),
      data: {
        label: (
          <div
            className="xy-workflow-node-content"
            onClick={(event) => {
              event.stopPropagation();
              onNodeClick?.(node);
            }}
          >
            <div className="xy-workflow-node-header">
              <Text strong className="xy-workflow-node-title">
                {node.title}
              </Text>
              <Tag className="xy-workflow-node-type" color={statusColor(status)}>
                {WORKFLOW_NODE_TYPE_LABEL[type] ?? type}
              </Tag>
            </div>
            <Text className="xy-workflow-node-meta" type="secondary">
              {state?.message || node.meta || node.role || "-"}
            </Text>
            <div className="xy-workflow-node-footer">
              <span style={{ backgroundColor: statusColor(status) }} />
              <Text
                className="xy-workflow-node-status"
                type={status === "failed" ? "danger" : "secondary"}
              >
                {status}
                {typeof state?.progress === "number"
                  ? ` / ${state.progress}%`
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
  selectedEdgeIds: string[] = [],
  invalidEdgeIssues: Map<string, WorkflowValidationIssue> = new Map(),
): FlowEdge[] {
  return (workflow.edges ?? [])
    .map((edge) => {
      const from = edgeSource(edge);
      const to = edgeTarget(edge);
      if (!from || !to) return undefined;
      const state = runtimeEdge(edge, latestRun);
      const status = normalizeStatus(
        state?.status ?? (Array.isArray(edge) ? "queued" : edge.status),
      );
      const condition = edgeCondition(edge);
      const id = edgeId(edge);
      const issue = invalidEdgeIssues.get(id);
      return {
        id,
        source: from,
        target: to,
        label: issue ? condition || "连线错误" : condition,
        selected: selectedEdgeIds.includes(id),
        data: { condition },
        className: issue ? "xy-workflow-edge-invalid" : undefined,
        animated: status === "running",
        markerEnd: { type: MarkerType.ArrowClosed },
        style: {
          stroke: issue ? "#ff4d4f" : statusColor(status),
          strokeWidth: issue || status === "running" ? 2.5 : 1.5,
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
  selectedNodeIds = [],
  selectedEdgeIds = [],
  validationIssues = [],
  fitViewSignal = 0,
  onChange,
  onDropNodeType,
  onNodeClick,
  onPaneClick,
  onSelectionChange,
  onCopySelection,
}: {
  workflow: ConversationWorkflow;
  latestRun?: WorkflowRun;
  locked?: boolean;
  overlayText?: string;
  selectedNodeIds?: string[];
  selectedEdgeIds?: string[];
  validationIssues?: WorkflowValidationIssue[];
  fitViewSignal?: number;
  onChange: (workflow: ConversationWorkflow) => void;
  onDropNodeType?: (type: string, position?: { x: number; y: number }) => void;
  onNodeClick: (node: WorkflowNode) => void;
  onPaneClick?: () => void;
  onSelectionChange?: (nodeIds: string[], edgeIds: string[]) => void;
  onCopySelection?: () => void;
}) {
  const lastNodePointerAt = useRef(0);
  const flowInstance = useRef<ReactFlowInstance | null>(null);
  const invalidNodeIds = useMemo(
    () =>
      new Set(
        validationIssues
          .map((issue) => issue.nodeId)
          .filter((id): id is string => Boolean(id)),
      ),
    [validationIssues],
  );
  const invalidEdgeIssues = useMemo(
    () =>
      new Map(
        validationIssues
          .filter((issue) => issue.edgeId)
          .map((issue) => [issue.edgeId!, issue]),
      ),
    [validationIssues],
  );
  const markNodePointer = useCallback(() => {
    lastNodePointerAt.current = Date.now();
  }, []);
  const flowNodes = useMemo(
    () =>
      layoutNodes(
        workflow,
        latestRun,
        selectedNodeIds,
        invalidNodeIds,
        onNodeClick,
      ),
    [workflow, latestRun, selectedNodeIds, invalidNodeIds, onNodeClick],
  );
  const flowEdges = useMemo(
    () => layoutEdges(workflow, latestRun, selectedEdgeIds, invalidEdgeIssues),
    [workflow, latestRun, selectedEdgeIds, invalidEdgeIssues],
  );
  const nodeById = useMemo(
    () => new Map((workflow.nodes ?? []).map((node) => [node.id, node])),
    [workflow.nodes],
  );

  useEffect(() => {
    if (!fitViewSignal || !flowInstance.current) return;
    flowInstance.current.fitView({ padding: 0.18 });
  }, [fitViewSignal]);

  const nodeFromEventTarget = (target: EventTarget | null) => {
    if (!(target instanceof HTMLElement)) return undefined;
    const nodeElement = target.closest(".react-flow__node");
    const nodeId = nodeElement?.getAttribute("data-id");
    return nodeId ? nodeById.get(nodeId) : undefined;
  };

  const handleNodesChange = (changes: NodeChange[]) => {
    if (locked) return;
    const structuralChanges = changes.filter((change) => {
      if (change.type === "remove") {
        const node = nodeById.get(change.id);
        return node && !["start", "end"].includes(workflowNodeType(node));
      }
      return change.type === "position";
    });
    if (!structuralChanges.length) return;
    const nextFlowNodes = applyNodeChanges(structuralChanges, flowNodes);
    const nextNodeIds = new Set(nextFlowNodes.map((node) => node.id));
    const positionById = new Map(
      nextFlowNodes.map((node) => [node.id, node.position]),
    );
    const nodes = workflow.nodes
      .filter((node) => nextNodeIds.has(node.id))
      .map((node) => ({
        ...node,
        position: positionById.get(node.id) ?? node.position,
      }));
    const edges = (workflow.edges ?? []).filter(
      (edge) =>
        nextNodeIds.has(edgeSource(edge)) && nextNodeIds.has(edgeTarget(edge)),
    );
    onChange({ ...workflow, nodes, edges });
  };

  const handleEdgesChange = (changes: EdgeChange[]) => {
    if (locked) return;
    const structuralChanges = changes.filter((change) => change.type !== "select");
    if (!structuralChanges.length) return;
    onChange({
      ...workflow,
      edges: applyEdgeChanges(structuralChanges, flowEdges).map(toWorkflowEdge),
    });
  };

  const handleConnect = (connection: Connection) => {
    if (locked || !connection.source || !connection.target) return;
    const nextEdges = addEdge(
      {
        ...connection,
        markerEnd: { type: MarkerType.ArrowClosed },
      },
      flowEdges,
    ).map(toWorkflowEdge);
    onChange({ ...workflow, edges: nextEdges });
  };

  const hasNodeDragPayload = (event: DragEvent<HTMLDivElement>) =>
    Array.from(event.dataTransfer.types).includes(
      "application/x-agenthub-node",
    );

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    if (locked || !onDropNodeType || !hasNodeDragPayload(event)) return;
    const type = event.dataTransfer.getData("application/x-agenthub-node");
    if (!type) return;
    event.preventDefault();
    const position =
      flowInstance.current?.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      }) ?? { x: event.clientX, y: event.clientY };
    onDropNodeType(type, position);
  };

  return (
    <div
      className="xy-workflow-canvas"
      tabIndex={0}
      onDragOver={(event) => {
        if (locked || !onDropNodeType || !hasNodeDragPayload(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }}
      onDrop={handleDrop}
      onClickCapture={(event) => {
        const workflowNode = nodeFromEventTarget(event.target);
        if (!workflowNode) return;
        markNodePointer();
        onNodeClick(workflowNode);
        event.stopPropagation();
      }}
      onMouseDownCapture={(event) => {
        if (nodeFromEventTarget(event.target)) markNodePointer();
      }}
      onKeyDown={(event) => {
        if (locked) return;
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
          event.preventDefault();
          onCopySelection?.();
        }
      }}
    >
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        connectionMode={ConnectionMode.Loose}
        deleteKeyCode={locked ? null : ["Backspace", "Delete"]}
        multiSelectionKeyCode={["Shift", "Control", "Meta"]}
        nodesDraggable={!locked}
        nodesConnectable={!locked}
        elementsSelectable={!locked}
        panOnScroll
        panOnDrag={!locked}
        selectionOnDrag={false}
        selectionKeyCode={locked ? null : "Shift"}
        selectionMode={SelectionMode.Partial}
        selectNodesOnDrag={false}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        onInit={(instance) => {
          flowInstance.current = instance;
        }}
        onNodeDragStart={markNodePointer}
        onSelectionChange={({ nodes, edges }) => {
          onSelectionChange?.(
            nodes.map((node) => node.id),
            edges.map((edge) => edge.id),
          );
        }}
        onNodeClick={(_, node) => {
          if (locked) return;
          const workflowNode = nodeById.get(node.id);
          if (workflowNode) onNodeClick(workflowNode);
        }}
        onPaneClick={() => {
          if (Date.now() - lastNodePointerAt.current < 250) return;
          onSelectionChange?.([], []);
          onPaneClick?.();
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
