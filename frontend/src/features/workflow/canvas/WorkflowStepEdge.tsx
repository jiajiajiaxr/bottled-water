import {
  EdgeLabelRenderer,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import type { MouseEvent, PointerEvent } from "react";

export type WorkflowStepEdgeData = {
  condition?: string;
  issueLabel?: string;
  statusColor: string;
  selected: boolean;
  onSelect?: (edgeId: string) => void;
};

export type WorkflowStepEdgeModel = Edge<
  WorkflowStepEdgeData,
  "workflowStep"
>;

function buildOrthogonalPath(
  sourceX: number,
  sourceY: number,
  targetX: number,
  targetY: number,
) {
  const distance = Math.abs(targetX - sourceX);
  const offset = targetX >= sourceX
    ? Math.max(56, distance / 2)
    : Math.max(72, Math.min(160, distance / 2 + 72));
  const midX = sourceX + offset;
  const labelX = midX;
  const labelY = sourceY + (targetY - sourceY) / 2;
  return {
    labelX,
    labelY,
    path: `M ${sourceX} ${sourceY} L ${midX} ${sourceY} L ${midX} ${targetY} L ${targetX} ${targetY}`,
  };
}

export function WorkflowStepEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  markerEnd,
  selected,
  data,
}: EdgeProps<WorkflowStepEdgeModel>) {
  const { path, labelX, labelY } = buildOrthogonalPath(
    sourceX,
    sourceY,
    targetX,
    targetY,
  );
  const isSelected = Boolean(selected || data?.selected);
  const hasIssue = Boolean(data?.issueLabel);
  const stroke = isSelected
    ? "#1677ff"
    : hasIssue
      ? "#ff4d4f"
      : data?.statusColor ?? "#d0d3d6";
  const label = data?.issueLabel ?? data?.condition;

  const selectEdge = (event: MouseEvent | PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const canvas = event.currentTarget.closest(".xy-workflow-canvas");
    if (canvas instanceof HTMLElement) canvas.focus();
    data?.onSelect?.(id);
  };

  return (
    <>
      <path
        d={path}
        fill="none"
        markerEnd={markerEnd}
        className="react-flow__edge-path xy-workflow-step-edge-path"
        style={{
          stroke,
          strokeWidth: isSelected || hasIssue ? 2.8 : 2,
        }}
      />
      <path
        d={path}
        fill="none"
        stroke="rgba(22, 119, 255, 0.02)"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={32}
        pointerEvents="stroke"
        className="xy-workflow-step-edge-hit"
        onClick={selectEdge}
        onMouseDown={selectEdge}
        onPointerDown={selectEdge}
      />
      {label && (
        <EdgeLabelRenderer>
          <div
            className="xy-workflow-step-edge-label nodrag nopan"
            style={{
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            }}
            onClick={selectEdge}
            onPointerDown={(event) => event.stopPropagation()}
          >
            <span>{label}</span>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
