import {
  BaseEdge,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";

export type WorkflowStepEdgeData = {
  condition?: string;
  issueLabel?: string;
  statusColor: string;
  selected: boolean;
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
  const distanceX = targetX - sourceX;
  const closeHorizontalPorts = distanceX >= 0 && distanceX < 96;
  if (closeHorizontalPorts) {
    if (Math.abs(targetY - sourceY) > 24) {
      const midX = sourceX + distanceX / 2;
      return {
        labelX: midX,
        labelY: sourceY + (targetY - sourceY) / 2,
        path: [
          `M ${sourceX} ${sourceY}`,
          `L ${midX} ${sourceY}`,
          `L ${midX} ${targetY}`,
          `L ${targetX} ${targetY}`,
        ].join(" "),
      };
    }

    const upperLaneY = Math.min(sourceY, targetY) - 72;
    const laneY = upperLaneY > 24
      ? upperLaneY
      : Math.max(sourceY, targetY) + 72;
    return {
      labelX: sourceX + (targetX - sourceX) / 2,
      labelY: laneY,
      path: [
        `M ${sourceX} ${sourceY}`,
        `L ${sourceX} ${laneY}`,
        `L ${targetX} ${laneY}`,
        `L ${targetX} ${targetY}`,
      ].join(" "),
    };
  }

  const distance = Math.abs(distanceX);
  const offset = distanceX >= 0
    ? distance / 2
    : Math.max(72, Math.min(160, distance / 2 + 72));
  const midX = sourceX + offset;
  return {
    labelX: midX,
    labelY: sourceY + (targetY - sourceY) / 2,
    path: `M ${sourceX} ${sourceY} L ${midX} ${sourceY} L ${midX} ${targetY} L ${targetX} ${targetY}`,
  };
}

export function WorkflowStepEdge({
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

  return (
    <BaseEdge
      path={path}
      labelX={labelX}
      labelY={labelY}
      label={label}
      labelShowBg
      labelStyle={{
        fill: hasIssue ? "#ff4d4f" : "#596579",
        fontSize: 12,
        fontWeight: hasIssue ? 600 : 400,
      }}
      labelBgPadding={[6, 4]}
      labelBgBorderRadius={6}
      labelBgStyle={{
        fill: "rgba(255, 255, 255, 0.96)",
        stroke: hasIssue ? "#ffccc7" : "#dbe3ef",
      }}
      markerEnd={markerEnd}
      interactionWidth={40}
      className="xy-workflow-step-edge-path"
      style={{
        stroke,
        strokeWidth: isSelected || hasIssue ? 2.8 : 2,
      }}
    />
  );
}
