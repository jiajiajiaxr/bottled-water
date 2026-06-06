import { RobotOutlined } from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { Space, Tag, Tooltip, Typography } from "antd";
import type {
  Conversation,
  ConversationRuntimeAgentRun,
  ConversationRuntimeDecision,
  ConversationRuntimeGeneration,
} from "@/types";

const { Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  queued: "default",
  idle: "default",
  ready: "default",
  running: "processing",
  paused: "warning",
  waiting: "warning",
  completed: "success",
  failed: "error",
  cancelled: "default",
  canceled: "default",
};

export function RuntimeDecisionStrip({
  conversation,
}: {
  conversation?: Conversation;
}) {
  const [expanded, setExpanded] = useState(false);
  const [position, setPosition] = useState<{ x: number; y: number }>();
  const widgetRef = useRef<HTMLDivElement>(null);
  const suppressClickRef = useRef(false);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    baseX: number;
    baseY: number;
    moved: boolean;
    cleanup: () => void;
  }>();
  const generation = latestGeneration(conversation);
  const conversationId = conversation?.id;

  useEffect(() => {
    setExpanded(false);
    setPosition(undefined);
  }, [conversationId]);

  useEffect(() => {
    return () => {
      dragRef.current?.cleanup();
      dragRef.current = undefined;
    };
  }, []);

  if (!generation) return null;

  const decision = latestDecision(generation);
  const agentRuns = generation.agent_runs || [];
  const status = effectiveGenerationStatus(conversation, generation);
  const agentNameMap = buildAgentNameMap(conversation);
  const isVisible =
    decision ||
    agentRuns.some((item) => item.status && item.status !== "queued") ||
    status === "running";
  if (!isVisible) return null;

  const onPointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    const widget = widgetRef.current;
    const panel = widget?.closest(".chat-panel") as HTMLElement | null;
    if (!widget || !panel) return;
    const widgetRect = widget.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const pointerId = event.pointerId;

    const onWindowPointerMove = (moveEvent: globalThis.PointerEvent) => {
      const drag = dragRef.current;
      const currentWidget = widgetRef.current;
      const currentPanel = currentWidget?.closest(".chat-panel") as HTMLElement | null;
      if (!drag || !currentWidget || !currentPanel || drag.pointerId !== moveEvent.pointerId) return;
      const dx = moveEvent.clientX - drag.startX;
      const dy = moveEvent.clientY - drag.startY;
      if (!drag.moved && Math.hypot(dx, dy) < 6) return;
      drag.moved = true;
      moveEvent.preventDefault();
      const maxX = Math.max(8, currentPanel.clientWidth - currentWidget.offsetWidth - 8);
      const maxY = Math.max(8, currentPanel.clientHeight - currentWidget.offsetHeight - 84);
      setPosition({
        x: clamp(drag.baseX + dx, 8, maxX),
        y: clamp(drag.baseY + dy, 8, maxY),
      });
    };

    const cleanup = () => {
      window.removeEventListener("pointermove", onWindowPointerMove);
      window.removeEventListener("pointerup", onWindowPointerUp);
      window.removeEventListener("pointercancel", onWindowPointerUp);
    };

    const onWindowPointerUp = (upEvent: globalThis.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag || drag.pointerId !== upEvent.pointerId) return;
      if (drag.moved) {
        suppressClickRef.current = true;
        window.setTimeout(() => {
          suppressClickRef.current = false;
        }, 0);
      }
      cleanup();
      dragRef.current = undefined;
    };

    window.addEventListener("pointermove", onWindowPointerMove, { passive: false });
    window.addEventListener("pointerup", onWindowPointerUp);
    window.addEventListener("pointercancel", onWindowPointerUp);
    dragRef.current = {
      pointerId,
      startX: event.clientX,
      startY: event.clientY,
      baseX: widgetRect.left - panelRect.left,
      baseY: widgetRect.top - panelRect.top,
      moved: false,
      cleanup,
    };
  };

  const toggleExpanded = () => {
    if (suppressClickRef.current) return;
    setExpanded((current) => !current);
  };

  const style = position
    ? { left: position.x, top: position.y, right: "auto" }
    : undefined;

  return (
    <div
      ref={widgetRef}
      className={[
        "runtime-decision-widget",
        expanded ? "expanded" : "collapsed",
        status === "running" ? "running" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      data-testid="runtime-decision-strip"
      style={style}
    >
      <button
        type="button"
        className="runtime-decision-trigger"
        aria-label={expanded ? "收起组织状态" : "展开组织状态"}
        onClick={toggleExpanded}
        onPointerDown={onPointerDown}
      >
        <RobotOutlined />
        {!expanded && status === "running" && <span className="runtime-decision-pulse" />}
      </button>
      {expanded && (
        <div className="runtime-decision-card">
          <button
            type="button"
            className="runtime-decision-card-head"
            onClick={toggleExpanded}
            onPointerDown={onPointerDown}
          >
            <span className="runtime-decision-card-icon">
              <RobotOutlined />
            </span>
            <span>
              <Text strong>{modeLabel(conversation)}</Text>
              <Text type="secondary" className="runtime-decision-card-subtitle">
                {status}
              </Text>
            </span>
          </button>
          <Space size={[8, 8]} wrap className="runtime-decision-card-body">
            {decision && (
              <DecisionTag decision={decision} agentNameMap={agentNameMap} />
            )}
            {agentRuns.slice(0, 5).map((run) => (
              <AgentRunTag
                key={run.agent_id}
                run={run}
                agentNameMap={agentNameMap}
              />
            ))}
            {agentRuns.length > 5 && (
              <Text type="secondary">等 {agentRuns.length} 个 Agent</Text>
            )}
          </Space>
        </div>
      )}
    </div>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function DecisionTag({
  decision,
  agentNameMap,
}: {
  decision: ConversationRuntimeDecision;
  agentNameMap: Map<string, string>;
}) {
  const targets = decision.target_agent_ids?.length
    ? decision.target_agent_ids.map((item) => agentLabel(item, agentNameMap)).join(", ")
    : decision.target
      ? agentLabel(decision.target, agentNameMap)
      : undefined;
  const label = [
    decision.round ? `第 ${decision.round} 轮` : "",
    decision.decision || "wait",
    targets ? `指派 ${targets}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const detail = [
    decision.rationale ? `原因：${decision.rationale}` : "",
    decision.task ? `任务：${decision.task}` : "",
    decision.expected_outputs?.length
      ? `期望：${decision.expected_outputs.join("、")}`
      : "",
    decision.fallback_reason ? `回退：${decision.fallback_reason}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <Tooltip title={detail || "Team Leader 调度决策"}>
      <Tag color="blue">{label}</Tag>
    </Tooltip>
  );
}

function AgentRunTag({
  run,
  agentNameMap,
}: {
  run: ConversationRuntimeAgentRun;
  agentNameMap: Map<string, string>;
}) {
  const status = String(run.status || "queued").toLowerCase();
  const name = displayAgentRunName(run, agentNameMap);
  const title = [
    run.current_task ? `任务：${run.current_task}` : "",
    run.rationale ? `说明：${run.rationale}` : "",
    run.error ? `错误：${run.error}` : "",
    run.output_preview ? `输出：${run.output_preview}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <Tooltip title={title || `${name} · ${status}`}>
      <Tag color={STATUS_COLOR[status] || "default"}>
        {name} · {status}
      </Tag>
    </Tooltip>
  );
}

function modeLabel(conversation?: Conversation): string {
  if (conversation?.chat_type === "single") return "单 Agent";
  return conversation?.workflow_enabled ? "工作流聊天" : "自动组织";
}

function buildAgentNameMap(conversation?: Conversation): Map<string, string> {
  const map = new Map<string, string>();
  for (const participant of conversation?.participants || []) {
    if (!participant.agent_id) continue;
    map.set(
      participant.agent_id,
      participant.agent_name ||
        participant.nickname ||
        participant.agent_id.slice(0, 8),
    );
  }
  return map;
}

function agentLabel(agentId: string, agentNameMap: Map<string, string>): string {
  if (
    agentId === "team_leader" ||
    agentId === "scheduler" ||
    agentId.startsWith("team_lea")
  ) {
    return "Team Leader";
  }
  return agentNameMap.get(agentId) || agentId.slice(0, 8);
}

function displayAgentRunName(
  run: ConversationRuntimeAgentRun,
  agentNameMap: Map<string, string>,
): string {
  const fallback = agentLabel(run.agent_id, agentNameMap);
  const name = String(run.agent_name || "").trim();
  if (!name) return fallback;
  if (name === run.agent_id || name === run.agent_id.slice(0, 8)) return fallback;
  return name;
}

function latestGeneration(
  conversation?: Conversation,
): ConversationRuntimeGeneration | undefined {
  const generations = conversation?.runtime?.generations || [];
  return generations.length ? generations[generations.length - 1] : undefined;
}

function effectiveGenerationStatus(
  conversation: Conversation | undefined,
  generation: ConversationRuntimeGeneration,
) {
  const conversationStatus = String(conversation?.generation_status || "").toLowerCase();
  const generationStatus = String(generation.status || "idle").toLowerCase();
  if (
    conversationStatus &&
    conversationStatus !== "running" &&
    generationStatus === "running"
  ) {
    return conversationStatus === "idle" ? "completed" : conversationStatus;
  }
  return generationStatus || "idle";
}

function latestDecision(
  generation: ConversationRuntimeGeneration,
): ConversationRuntimeDecision | undefined {
  const decisions = generation.decisions || [];
  return decisions.length ? decisions[decisions.length - 1] : undefined;
}
