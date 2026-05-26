export type WorkflowConnectionDraft = {
  sourceId: string;
  sourcePoint: { x: number; y: number };
  pointerPoint: { x: number; y: number };
  targetId?: string;
};

function previewPath(
  sourcePoint: WorkflowConnectionDraft["sourcePoint"],
  pointerPoint: WorkflowConnectionDraft["pointerPoint"],
) {
  const distance = Math.abs(pointerPoint.x - sourcePoint.x);
  const controlOffset = Math.max(72, Math.min(220, distance * 0.55));
  return [
    `M ${sourcePoint.x} ${sourcePoint.y}`,
    `C ${sourcePoint.x + controlOffset} ${sourcePoint.y}`,
    `${pointerPoint.x - controlOffset} ${pointerPoint.y}`,
    `${pointerPoint.x} ${pointerPoint.y}`,
  ].join(" ");
}

export function WorkflowConnectionPreview({
  draft,
}: {
  draft?: WorkflowConnectionDraft;
}) {
  if (!draft) return null;
  return (
    <svg className="xy-workflow-connection-preview" aria-hidden="true">
      <path
        d={previewPath(draft.sourcePoint, draft.pointerPoint)}
        className="xy-workflow-connection-preview-path"
      />
      <circle
        cx={draft.pointerPoint.x}
        cy={draft.pointerPoint.y}
        r={draft.targetId ? 6 : 4}
        className={
          draft.targetId
            ? "xy-workflow-connection-preview-dot is-valid"
            : "xy-workflow-connection-preview-dot"
        }
      />
    </svg>
  );
}
