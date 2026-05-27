import type { PointerEvent } from "react";

export function ResizeHandle({
  onResizeStart,
}: {
  onResizeStart: (event: PointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className="preview-resize-handle"
      onPointerDown={onResizeStart}
      role="separator"
      aria-orientation="vertical"
      aria-label="调整预览栏宽度"
    />
  );
}
