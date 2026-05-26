import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from "react";
import type { WorkflowConnectionDraft } from "./WorkflowConnectionPreview";

function pointInContainer(
  event: MouseEvent | PointerEvent | ReactMouseEvent<HTMLElement> | ReactPointerEvent<HTMLElement>,
  container: HTMLElement,
) {
  const rect = container.getBoundingClientRect();
  return {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
}

function portCenterInContainer(port: HTMLElement, container: HTMLElement) {
  const portRect = port.getBoundingClientRect();
  const canvasRect = container.getBoundingClientRect();
  return {
    x: portRect.left + portRect.width / 2 - canvasRect.left,
    y: portRect.top + portRect.height / 2 - canvasRect.top,
  };
}

function inputPortNodeIdAt(event: MouseEvent | PointerEvent) {
  const element = document.elementFromPoint(event.clientX, event.clientY);
  if (!(element instanceof HTMLElement)) return undefined;
  const port = element.closest<HTMLElement>(
    '[data-workflow-port="input"][data-node-id]',
  );
  return port?.dataset.nodeId;
}

export function useManualWorkflowConnection({
  canvasRef,
  locked,
  canConnect,
  onConnect,
}: {
  canvasRef: RefObject<HTMLDivElement>;
  locked: boolean;
  canConnect: (sourceId: string, targetId: string) => boolean;
  onConnect: (sourceId: string, targetId: string) => void;
}) {
  const [draft, setDraft] = useState<WorkflowConnectionDraft>();
  const [armedSource, setArmedSource] = useState<{
    sourceId: string;
    sourcePoint: { x: number; y: number };
  }>();
  const draftRef = useRef<WorkflowConnectionDraft>();
  const armedSourceRef = useRef<typeof armedSource>();
  const canConnectRef = useRef(canConnect);
  const onConnectRef = useRef(onConnect);

  useEffect(() => {
    canConnectRef.current = canConnect;
    onConnectRef.current = onConnect;
  }, [canConnect, onConnect]);

  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    armedSourceRef.current = armedSource;
  }, [armedSource]);

  const startConnection = useCallback(
    (sourceId: string, event: ReactPointerEvent<HTMLElement>) => {
      if (locked || event.button !== 0 || !canvasRef.current) return;
      const sourcePort = event.currentTarget;
      sourcePort.setPointerCapture?.(event.pointerId);
      event.preventDefault();
      event.stopPropagation();
      setDraft({
        sourceId,
        sourcePoint: portCenterInContainer(sourcePort, canvasRef.current),
        pointerPoint: pointInContainer(event, canvasRef.current),
      });
    },
    [canvasRef, locked],
  );
  const armConnection = useCallback(
    (sourceId: string, event: ReactMouseEvent<HTMLElement>) => {
      if (locked || !canvasRef.current) return;
      event.preventDefault();
      event.stopPropagation();
      setDraft(undefined);
      setArmedSource({
        sourceId,
        sourcePoint: portCenterInContainer(event.currentTarget, canvasRef.current),
      });
    },
    [canvasRef, locked],
  );
  const completeArmedConnection = useCallback(
    (
      targetId: string,
      event: ReactMouseEvent<HTMLElement> | ReactPointerEvent<HTMLElement>,
    ) => {
      event.preventDefault();
      event.stopPropagation();
      const currentArmedSource = armedSourceRef.current;
      if (locked || !currentArmedSource) return;
      onConnectRef.current(currentArmedSource.sourceId, targetId);
      setArmedSource(undefined);
    },
    [locked],
  );
  const startConnectionFromMouse = useCallback(
    (sourceId: string, event: ReactMouseEvent<HTMLElement>) => {
      if (locked || event.button !== 0 || !canvasRef.current) return;
      event.preventDefault();
      event.stopPropagation();
      setDraft({
        sourceId,
        sourcePoint: portCenterInContainer(event.currentTarget, canvasRef.current),
        pointerPoint: pointInContainer(event, canvasRef.current),
      });
    },
    [canvasRef, locked],
  );

  const cancelConnection = useCallback(() => {
    setDraft(undefined);
    setArmedSource(undefined);
  }, []);

  useEffect(() => {
    if (!draft || locked) return undefined;

    const handleMove = (event: MouseEvent | PointerEvent) => {
      const current = draftRef.current;
      const container = canvasRef.current;
      if (!current || !container) return;
      const targetId = inputPortNodeIdAt(event);
      setDraft({
        ...current,
        pointerPoint: pointInContainer(event, container),
        targetId:
          targetId && canConnectRef.current(current.sourceId, targetId)
            ? targetId
            : undefined,
      });
    };

    const handleUp = (event: MouseEvent | PointerEvent) => {
      const current = draftRef.current;
      const targetId = current ? inputPortNodeIdAt(event) : undefined;
      if (
        current &&
        targetId &&
        canConnectRef.current(current.sourceId, targetId)
      ) {
        onConnectRef.current(current.sourceId, targetId);
      }
      setDraft(undefined);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") cancelConnection();
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [cancelConnection, canvasRef, draft, locked]);

  return {
    connectingSourceId: draft?.sourceId ?? armedSource?.sourceId,
    connectingTargetId: draft?.targetId,
    draftConnection: draft,
    isConnectionArmed: Boolean(armedSource),
    armConnection,
    completeArmedConnection,
    startConnection,
    startConnectionFromMouse,
    cancelConnection,
  };
}
