import { useCallback, useEffect, useMemo, useRef, type DragEvent } from "react";
import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  ConnectionMode,
  ConnectionLineType,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  SelectionMode,
  type Connection,
  type Edge as FlowEdge,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Spin, Typography } from "antd";
import type {
  ConversationWorkflow,
  WorkflowNode,
  WorkflowRun,
} from "../../../../types";
import { workflowNodeType } from "../../../../lib/workflow";
import { edgeId, edgeSource, edgeTarget } from "../../../workflow/utils";
import type { WorkflowValidationIssue } from "../../../workflow/validation";
import {
  layoutWorkflowCanvasEdges,
  layoutWorkflowCanvasNodes,
  toWorkflowEdge,
} from "../../../workflow/canvas/workflowCanvasElements";
import { WorkflowFlowNode } from "../../../workflow/canvas/WorkflowFlowNode";

const { Text } = Typography;
type WorkflowFlowInstance = {
  fitView: (options?: { padding?: number }) => void;
  screenToFlowPosition: (position: { x: number; y: number }) => {
    x: number;
    y: number;
  };
};

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
  const flowInstance = useRef<WorkflowFlowInstance | null>(null);
  const invalidNodeIds = useMemo(
    () =>
      new Set(
        validationIssues
          .filter((issue) => issue.severity === "error")
          .map((issue) => issue.nodeId)
          .filter((id): id is string => Boolean(id)),
      ),
    [validationIssues],
  );
  const warningNodeIds = useMemo(
    () =>
      new Set(
        validationIssues
          .filter((issue) => issue.severity === "warning")
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
      layoutWorkflowCanvasNodes(
        workflow,
        latestRun,
        selectedNodeIds,
        invalidNodeIds,
        warningNodeIds,
        onNodeClick,
      ),
    [
      workflow,
      latestRun,
      selectedNodeIds,
      invalidNodeIds,
      warningNodeIds,
      onNodeClick,
    ],
  );
  const flowEdges = useMemo(
    () =>
      layoutWorkflowCanvasEdges(
        workflow,
        latestRun,
        selectedEdgeIds,
        invalidEdgeIssues,
      ),
    [workflow, latestRun, selectedEdgeIds, invalidEdgeIssues],
  );
  const nodeById = useMemo(
    () => new Map((workflow.nodes ?? []).map((node) => [node.id, node])),
    [workflow.nodes],
  );
  const edgeKeys = useMemo(
    () =>
      new Set(
        (workflow.edges ?? []).map((edge) => `${edgeSource(edge)}->${edgeTarget(edge)}`),
      ),
    [workflow.edges],
  );
  const nodeTypes = useMemo(() => ({ workflow: WorkflowFlowNode }), []);

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
    if (!isValidConnection(connection)) return;
    const nextEdges = addEdge(
      {
        ...connection,
        id: `${connection.source}-${connection.target}-edge`,
        sourceHandle: connection.sourceHandle ?? "output",
        targetHandle: connection.targetHandle ?? "input",
        markerEnd: { type: MarkerType.ArrowClosed },
      },
      flowEdges,
    ).map(toWorkflowEdge);
    onChange({ ...workflow, edges: nextEdges });
  };

  const isValidConnection = (connection: Connection | FlowEdge) => {
    if (locked || !connection.source || !connection.target) return false;
    if (connection.source === connection.target) return false;
    if ((connection.sourceHandle ?? null) !== "output") return false;
    if ((connection.targetHandle ?? null) !== "input") return false;
    const source = nodeById.get(connection.source);
    const target = nodeById.get(connection.target);
    if (!source || !target) return false;
    if (workflowNodeType(source) === "end") return false;
    if (workflowNodeType(target) === "start") return false;
    return !edgeKeys.has(`${connection.source}->${connection.target}`);
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

  const deleteSelectedElements = () => {
    if (locked || (!selectedNodeIds.length && !selectedEdgeIds.length)) return;
    const protectedIds = new Set(
      workflow.nodes
        .filter((node) => ["start", "end"].includes(workflowNodeType(node)))
        .map((node) => node.id),
    );
    const removableNodeIds = new Set(
      selectedNodeIds.filter((id) => !protectedIds.has(id)),
    );
    const removableEdgeIds = new Set(selectedEdgeIds);
    const nodes = workflow.nodes.filter((node) => !removableNodeIds.has(node.id));
    const edges = (workflow.edges ?? []).filter((edge) => {
      if (removableEdgeIds.has(edgeId(edge))) return false;
      return (
        !removableNodeIds.has(edgeSource(edge)) &&
        !removableNodeIds.has(edgeTarget(edge))
      );
    });
    onSelectionChange?.([], []);
    onChange({ ...workflow, nodes, edges });
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
        const target = event.target;
        if (target instanceof HTMLElement) {
          const edgeElement = target.closest(".react-flow__edge");
          const edgeDomId = edgeElement?.getAttribute("data-id");
          if (edgeDomId) {
            event.currentTarget.focus();
            onSelectionChange?.([], [edgeDomId]);
            event.stopPropagation();
            return;
          }
        }
        const workflowNode = nodeFromEventTarget(event.target);
        if (!workflowNode) return;
        event.currentTarget.focus();
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
        if (event.key === "Delete" || event.key === "Backspace") {
          event.preventDefault();
          deleteSelectedElements();
        }
      }}
    >
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        connectionMode={ConnectionMode.Strict}
        connectionLineType={ConnectionLineType.SmoothStep}
        connectionLineStyle={{ stroke: "#d0d3d6", strokeWidth: 2.6 }}
        connectOnClick={false}
        deleteKeyCode={locked ? null : ["Backspace", "Delete"]}
        multiSelectionKeyCode={["Shift", "Control", "Meta"]}
        nodesDraggable={!locked}
        nodesConnectable={!locked}
        edgesFocusable={!locked}
        elementsSelectable={!locked}
        elevateEdgesOnSelect
        panOnScroll
        panOnDrag={!locked}
        selectionOnDrag={false}
        selectionKeyCode={locked ? null : "Shift"}
        selectionMode={SelectionMode.Partial}
        selectNodesOnDrag={false}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        isValidConnection={isValidConnection}
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
        onEdgeClick={(_, edge) => {
          if (locked) return;
          onSelectionChange?.([], [edge.id]);
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
