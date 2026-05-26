import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import type { MouseEvent, PointerEvent } from "react";

export type WorkflowFlowEdgeData = {
  condition?: string;
  issueLabel?: string;
  statusColor: string;
  selected: boolean;
  onDelete?: (edgeId: string) => void;
  onSelect?: (edgeId: string) => void;
};

export type WorkflowFlowEdgeModel = Edge<WorkflowFlowEdgeData, "workflowEdge">;

export function WorkflowFlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  selected,
  data,
}: EdgeProps<WorkflowFlowEdgeModel>) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 14,
  });
  const isSelected = selected || data?.selected;
  const stroke = isSelected ? "#1677ff" : data?.issueLabel ? "#ff4d4f" : "#d0d3d6";
  const label = data?.issueLabel ?? data?.condition;

  const selectEdge = (event: PointerEvent | MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    data?.onSelect?.(id);
  };

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className="xy-workflow-edge-visible"
        style={{
          stroke,
          strokeWidth: isSelected || data?.issueLabel ? 2.8 : 2.2,
        }}
      />
      <path
        d={path}
        fill="none"
        stroke="transparent"
        strokeWidth={30}
        className="xy-workflow-edge-hit"
        onClick={selectEdge}
        onPointerDown={selectEdge}
      />
      {(label || isSelected) && (
        <EdgeLabelRenderer>
          <div
            className="xy-workflow-edge-label nodrag nopan"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
            onPointerDown={(event) => event.stopPropagation()}
          >
            {label && <span>{label}</span>}
            {isSelected && (
              <button
                type="button"
                className="xy-workflow-edge-delete"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  data?.onDelete?.(id);
                }}
              >
                删除
              </button>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
