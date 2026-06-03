import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import {
  applyNodeChanges,
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  SelectionMode,
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
} from "../../../workflow/canvas/workflowCanvasElements";
import { WorkflowConnectionPreview } from "../../../workflow/canvas/WorkflowConnectionPreview";
import { WorkflowFlowNode } from "../../../workflow/canvas/WorkflowFlowNode";
import { WorkflowStepEdge } from "../../../workflow/canvas/WorkflowStepEdge";
import {
  canCreateWorkflowEdge,
  createWorkflowEdge,
} from "../../../workflow/canvas/workflowConnectionRules";
import { useManualWorkflowConnection } from "../../../workflow/canvas/useManualWorkflowConnection";

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
  onDeleteSelection,
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
  onDeleteSelection?: (removedNodeIds: string[]) => void;
}) {
  const lastNodePointerAt = useRef(0);
  const canvasRef = useRef<HTMLDivElement>(null);
  const flowInstance = useRef<WorkflowFlowInstance | null>(null);
  const armedSourceIdRef = useRef<string>();
  const [armedSourceId, setArmedSourceId] = useState<string>();
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
  const nodeById = useMemo(
    () => new Map((workflow.nodes ?? []).map((node) => [String(node.id), node])),
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
  const edgeTypes = useMemo(() => ({ workflowStep: WorkflowStepEdge }), []);
  const canConnectNodes = useCallback(
    (sourceId?: string | null, targetId?: string | null) =>
      canCreateWorkflowEdge({
        sourceId,
        targetId,
        nodeById,
        edgeKeys,
        locked,
      }),
    [edgeKeys, locked, nodeById],
  );
  const handleEdgeSelect = useCallback(
    (edgeIdValue: string) => {
      onSelectionChange?.([], [edgeIdValue]);
    },
    [onSelectionChange],
  );
  const handleManualConnect = useCallback(
    (sourceId: string, targetId: string) => {
      if (locked || sourceId === targetId) return;
      const source = nodeById.get(sourceId);
      const target = nodeById.get(targetId);
      if (!source || !target) return;
      if (workflowNodeType(source) === "end") return;
      if (workflowNodeType(target) === "start") return;
      if (
        (workflow.edges ?? []).some(
          (edge) =>
            edgeSource(edge) === sourceId && edgeTarget(edge) === targetId,
        )
      ) {
        return;
      }
      const nextEdge = createWorkflowEdge(sourceId, targetId);
      onSelectionChange?.([], [edgeId(nextEdge)]);
      armedSourceIdRef.current = undefined;
      setArmedSourceId(undefined);
      onChange({
        ...workflow,
        edges: [...(workflow.edges ?? []), nextEdge],
      });
    },
    [locked, nodeById, onChange, onSelectionChange, workflow],
  );
  const {
    connectingSourceId: dragSourceId,
    connectingTargetId,
    draftConnection,
    armConnection,
    cancelConnection,
    completeArmedConnection,
    startConnection,
    startConnectionFromMouse,
  } = useManualWorkflowConnection({
    canvasRef,
    locked,
    canConnect: canConnectNodes,
    onConnect: handleManualConnect,
  });
  const connectingSourceId = dragSourceId ?? armedSourceId;
  const canConnectToNode = useCallback(
    (nodeId: string) =>
      connectingSourceId ? canConnectNodes(connectingSourceId, nodeId) : false,
    [canConnectNodes, connectingSourceId],
  );
  const flowNodes = useMemo(
    () =>
      layoutWorkflowCanvasNodes(
        workflow,
        latestRun,
        selectedNodeIds,
        invalidNodeIds,
        warningNodeIds,
        onNodeClick,
        {
          connectingSourceId,
          connectingTargetId,
          canConnectToNode,
          onStartConnection: startConnection,
          onStartConnectionFromMouse: startConnectionFromMouse,
          onArmConnection: armConnection,
          onCompleteConnection: completeArmedConnection,
        },
      ),
    [
      workflow,
      latestRun,
      selectedNodeIds,
      invalidNodeIds,
      warningNodeIds,
      onNodeClick,
      connectingSourceId,
      connectingTargetId,
      canConnectToNode,
      armConnection,
      completeArmedConnection,
      startConnection,
      startConnectionFromMouse,
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
    [
      workflow,
      latestRun,
      selectedEdgeIds,
      invalidEdgeIssues,
    ],
  );

  useEffect(() => {
    if (!fitViewSignal || !flowInstance.current) return;
    flowInstance.current.fitView({ padding: 0.18 });
  }, [fitViewSignal]);

  useEffect(() => {
    armedSourceIdRef.current = armedSourceId;
  }, [armedSourceId]);

  const nodeFromEventTarget = (target: EventTarget | null) => {
    if (!(target instanceof HTMLElement)) return undefined;
    const nodeElement = target.closest(".react-flow__node");
    const nodeId = nodeElement?.getAttribute("data-id");
    return nodeId ? nodeById.get(nodeId) : undefined;
  };

  const handleNodesChange = (changes: NodeChange[]) => {
    if (locked) return;
    const removedNodeIds: string[] = [];
    const structuralChanges = changes.filter((change) => {
      if (change.type === "remove") {
        const node = nodeById.get(String(change.id));
        if (node && !["start", "end"].includes(workflowNodeType(node))) {
          removedNodeIds.push(String(change.id));
          return true;
        }
        return false;
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
      .filter((node) => nextNodeIds.has(String(node.id)))
      .map((node) => ({
        ...node,
        position: positionById.get(String(node.id)) ?? node.position,
      }));
    const edges = (workflow.edges ?? []).filter(
      (edge) =>
        nextNodeIds.has(edgeSource(edge)) && nextNodeIds.has(edgeTarget(edge)),
    );
    onChange({ ...workflow, nodes, edges });
    if (removedNodeIds.length) {
      onDeleteSelection?.(removedNodeIds);
    }
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

  const completePortConnection = (target: EventTarget | null) => {
    const sourceId = armedSourceIdRef.current;
    if (!(target instanceof HTMLElement) || !sourceId) return false;
    const port = target.closest(".xy-workflow-port") as HTMLElement | null;
    if (port?.dataset.workflowPort !== "input" || !port.dataset.nodeId) {
      return false;
    }
    handleManualConnect(sourceId, port.dataset.nodeId);
    return true;
  };

  const deleteSelectedElements = () => {
    if (locked || (!selectedNodeIds.length && !selectedEdgeIds.length)) return;
    const protectedIds = new Set(
      workflow.nodes
        .filter((node) => ["start", "end"].includes(workflowNodeType(node)))
        .map((node) => String(node.id)),
    );
    const removableNodeIds = new Set(
      selectedNodeIds.filter((id) => !protectedIds.has(id)),
    );
    const removableEdgeIds = new Set(selectedEdgeIds);
    const nodes = workflow.nodes.filter(
      (node) => !removableNodeIds.has(String(node.id)),
    );
    const edges = (workflow.edges ?? []).filter((edge) => {
      if (removableEdgeIds.has(edgeId(edge))) return false;
      return (
        !removableNodeIds.has(edgeSource(edge)) &&
        !removableNodeIds.has(edgeTarget(edge))
      );
    });
    onSelectionChange?.([], []);
    onChange({ ...workflow, nodes, edges });
    onDeleteSelection?.(Array.from(removableNodeIds));
  };

  return (
    <div
      ref={canvasRef}
      className={[
        "xy-workflow-canvas",
        draftConnection || armedSourceId ? "is-connecting" : "",
      ]
        .filter(Boolean)
        .join(" ")}
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
          const port = target.closest(".xy-workflow-port") as HTMLElement | null;
          if (port) {
            const nodeId = port.dataset.nodeId;
            const portType = port.dataset.workflowPort;
            event.preventDefault();
            event.stopPropagation();
            if (!nodeId) return;
            if (portType === "output") {
              setArmedSourceId((current) => {
                const next = current === nodeId ? undefined : nodeId;
                armedSourceIdRef.current = next;
                return next;
              });
              onSelectionChange?.([], []);
              return;
            }
            if (portType === "input" && armedSourceIdRef.current) {
              handleManualConnect(armedSourceIdRef.current, nodeId);
            }
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
        if (completePortConnection(event.target)) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        if (nodeFromEventTarget(event.target)) markNodePointer();
      }}
      onPointerDownCapture={(event) => {
        if (completePortConnection(event.target)) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
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
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.18 }}
        connectOnClick={false}
        deleteKeyCode={null}
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
        onEdgeClick={(event, edge) => {
          if (locked) return;
          event.stopPropagation();
          canvasRef.current?.focus();
          handleEdgeSelect(edge.id);
        }}
        onPaneClick={() => {
          if (Date.now() - lastNodePointerAt.current < 250) return;
          cancelConnection();
          armedSourceIdRef.current = undefined;
          setArmedSourceId(undefined);
          onSelectionChange?.([], []);
          onPaneClick?.();
        }}
      >
        <MiniMap pannable zoomable nodeStrokeWidth={3} />
        <Controls />
        <Background gap={20} />
      </ReactFlow>
      <WorkflowConnectionPreview draft={draftConnection} />
      {overlayText && (
        <div className="xy-workflow-overlay">
          <Spin />
          <Text strong>{overlayText}</Text>
        </div>
      )}
    </div>
  );
}
