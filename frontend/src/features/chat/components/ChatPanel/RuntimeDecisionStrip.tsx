import {
  CheckCircleFilled,
  ClockCircleOutlined,
  CloseCircleFilled,
  LoadingOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { Space, Tag, Tooltip, Typography } from "antd";
import type {
  Conversation,
  ConversationRuntimeAgentRun,
  ConversationRuntimeDecision,
  ConversationRuntimeGeneration,
  ConversationRuntimeSummary,
  ConversationRuntimeTaskPlanItem,
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
  const taskPlan = visibleTaskPlan(
    generation.task_plan || generation.summary?.plan || [],
    agentRuns,
  );
  const summary = generation.summary;
  const status = effectiveGenerationStatus(conversation, generation);
  const agentNameMap = buildAgentNameMap(conversation);
  const isVisible =
    decision ||
    taskPlan.length > 0 ||
    summary ||
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
          <div className="runtime-decision-card-body">
            {taskPlan.length > 1 && (
              <PlanProgress
                plan={taskPlan}
                agentRuns={agentRuns}
                agentNameMap={agentNameMap}
              />
            )}
            <Space size={[8, 8]} wrap className="runtime-decision-tags">
              {taskPlan.length > 0 && (
                <PlanTag
                  plan={taskPlan}
                  agentRuns={agentRuns}
                  agentNameMap={agentNameMap}
                />
              )}
              {decision && (
                <DecisionTag decision={decision} agentNameMap={agentNameMap} />
              )}
              {summary && <SummaryTag summary={summary} agentNameMap={agentNameMap} />}
              {generation.error && (
                <Tooltip title={generation.error}>
                  <Tag color="error">终止原因：{generation.error}</Tag>
                </Tooltip>
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
        </div>
      )}
    </div>
  );
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function visibleTaskPlan(
  plan: ConversationRuntimeTaskPlanItem[],
  agentRuns: ConversationRuntimeAgentRun[],
): ConversationRuntimeTaskPlanItem[] {
  if (plan.length > 0) return plan;
  if (agentRuns.length <= 1) return [];
  return agentRuns.map((run, index) => ({
    id: `run-${run.agent_id || index}`,
    agent_id: run.agent_id,
    agent_name: run.agent_name,
    role: run.role,
    priority: index + 1,
    status: run.status || "queued",
    task: fallbackTaskForRun(run, run.agent_name || run.agent_id || `Agent ${index + 1}`),
    output_preview: run.output_preview,
  }));
}

function fallbackTaskForRun(run: ConversationRuntimeAgentRun, name: string): string {
  const status = normalizedPlanStatus(run.status || "queued");
  if (status === "completed") return `${name} 已回报专项成果`;
  if (status === "running") return `${name} 正在处理专项任务`;
  if (status === "failed") return `${name} 需要复核失败原因`;
  return `等待 ${name} 回报`;
}

function PlanTag({
  plan,
  agentRuns,
  agentNameMap,
}: {
  plan: ConversationRuntimeTaskPlanItem[];
  agentRuns: ConversationRuntimeAgentRun[];
  agentNameMap: Map<string, string>;
}) {
  const rows = planRows(plan, agentRuns, agentNameMap);
  const completed = rows.filter((item) => item.status === "completed").length;
  const failed = rows.filter((item) => item.status === "failed").length;
  const detail = plan
    .map((item, index) => {
      const row = rows[index];
      const name = row?.name || item.agent_name || `Agent ${index + 1}`;
      return [
        `${index + 1}. ${name} [${statusLabel(row?.status || item.status || "queued")}]`,
        item.stage ? `阶段：${item.stage}` : "",
        item.depends_on?.length
          ? `依赖：${item.depends_on.map((id) => agentLabel(id, agentNameMap)).join("、")}`
          : "",
        item.task ? `任务：${shortText(item.task, 160)}` : "",
        item.expected_outputs?.length ? `期望：${item.expected_outputs.join("、")}` : "",
        item.output_preview ? `输出：${shortText(item.output_preview, 160)}` : "",
      ].filter(Boolean).join("\n");
    })
    .join("\n\n");
  const color = failed ? "error" : completed === plan.length ? "success" : "geekblue";
  return (
    <Tooltip title={detail || "自动组织任务计划"}>
      <Tag color={color}>计划 {completed}/{plan.length}</Tag>
    </Tooltip>
  );
}

function PlanProgress({
  plan,
  agentRuns,
  agentNameMap,
}: {
  plan: ConversationRuntimeTaskPlanItem[];
  agentRuns: ConversationRuntimeAgentRun[];
  agentNameMap: Map<string, string>;
}) {
  const rows = planRows(plan, agentRuns, agentNameMap);
  const completed = rows.filter((item) => item.status === "completed").length;
  const failed = rows.filter((item) => item.status === "failed").length;
  return (
    <section className="runtime-decision-progress" aria-label="组织任务进度">
      <div className="runtime-decision-progress-head">
        <Text type="secondary">进度</Text>
        <Text type={failed ? "danger" : "secondary"} className="runtime-decision-progress-count">
          {completed}/{rows.length}
        </Text>
      </div>
      <ol className="runtime-decision-progress-list">
        {rows.map((row) => (
          <li
            key={row.id}
            className={`runtime-decision-progress-item ${row.status}`}
          >
            <span className="runtime-decision-progress-icon" aria-hidden="true">
              {statusIcon(row.status)}
            </span>
            <Tooltip title={row.detail}>
              <span className="runtime-decision-progress-text">
                <span className="runtime-decision-progress-title">{row.title}</span>
                <span className="runtime-decision-progress-meta">
                  {row.name} · {statusLabel(row.status)}
                </span>
              </span>
            </Tooltip>
          </li>
        ))}
      </ol>
    </section>
  );
}

function SummaryTag({
  summary,
  agentNameMap,
}: {
  summary: ConversationRuntimeSummary;
  agentNameMap: Map<string, string>;
}) {
  const failed = summary.failed_agent_ids || [];
  const pending = summary.pending_agent_ids || [];
  const inflight = summary.inflight_agent_ids || [];
  const completed = summary.completed_agent_ids || [];
  const gaps = summary.coordination_gaps || [];
  const detail = [
    summary.task ? `用户需求：${shortText(summary.task, 180)}` : "",
    completed.length ? `已完成：${completed.map((id) => agentLabel(id, agentNameMap)).join("、")}` : "",
    inflight.length ? `运行中：${inflight.map((id) => agentLabel(id, agentNameMap)).join("、")}` : "",
    pending.length ? `待回报：${pending.map((id) => agentLabel(id, agentNameMap)).join("、")}` : "",
    failed.length ? `失败：${failed.map((id) => agentLabel(id, agentNameMap)).join("、")}` : "",
    gaps.length ? `协作缺口：${gaps.map((item) => shortText(item, 120)).join("；")}` : "",
    summary.final_answer ? `汇总：${shortText(summary.final_answer, 260)}` : "",
  ].filter(Boolean).join("\n");
  const status = String(summary.status || "partial").toLowerCase();
  const color = status.includes("fail") ? "error" : status === "completed" ? "success" : "processing";
  return (
    <Tooltip title={detail || "自动组织运行汇总"}>
      <Tag color={color}>汇总 {summary.status || "partial"}</Tag>
    </Tooltip>
  );
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
    run.input ? `输入：${shortText(formatRecord(run.input), 180)}` : "",
    run.rationale ? `说明：${run.rationale}` : "",
    run.error ? `错误：${run.error}` : "",
    run.output ? `输出：${shortText(formatRecord(run.output), 180)}` : "",
    run.output_preview ? `输出：${run.output_preview}` : "",
    typeof run.tool_count === "number" ? `工具调用：${run.tool_count}` : "",
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <Tooltip title={title || `${name} · ${status}`}>
      <Tag color={STATUS_COLOR[status] || "default"}>
        {name} · {status}
        {typeof run.tool_count === "number" && run.tool_count > 0 ? ` · tools ${run.tool_count}` : ""}
      </Tag>
    </Tooltip>
  );
}

type PlanProgressRow = {
  id: string;
  name: string;
  title: string;
  detail: string;
  status: string;
};

function planRows(
  plan: ConversationRuntimeTaskPlanItem[],
  agentRuns: ConversationRuntimeAgentRun[],
  agentNameMap: Map<string, string>,
): PlanProgressRow[] {
  const runMap = new Map(agentRuns.map((run) => [run.agent_id, run]));
  return plan.map((item, index) => {
    const run = item.agent_id ? runMap.get(item.agent_id) : undefined;
    const status = normalizedPlanStatus(run?.status || item.status || "queued");
    const name = item.agent_id
      ? item.agent_name || agentLabel(item.agent_id, agentNameMap)
      : item.agent_name || `Agent ${index + 1}`;
    const task = item.task || run?.current_task || item.rationale || name;
    const title = shortTaskTitle(task, name);
    const detail = [
      `Agent：${name}`,
      `状态：${statusLabel(status)}`,
      item.stage ? `阶段：${item.stage}` : "",
      item.depends_on?.length
        ? `依赖：${item.depends_on.map((id) => agentLabel(id, agentNameMap)).join("、")}`
        : "",
      task ? `任务：${shortText(task, 220)}` : "",
      item.expected_outputs?.length ? `期望：${item.expected_outputs.join("、")}` : "",
      run?.output_preview || item.output_preview
        ? `输出：${shortText(run?.output_preview || item.output_preview || "", 180)}`
        : "",
      run?.error ? `错误：${run.error}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    return {
      id: item.id || item.agent_id || `${index}`,
      name,
      title,
      detail,
      status,
    };
  });
}

function normalizedPlanStatus(status: string): string {
  const normalized = String(status || "queued").toLowerCase();
  if (["completed", "failed", "cancelled", "canceled", "running", "waiting", "paused"].includes(normalized)) {
    return normalized === "canceled" ? "cancelled" : normalized;
  }
  if (["ready", "idle"].includes(normalized)) return "queued";
  return "queued";
}

function statusIcon(status: string) {
  if (status === "completed") return <CheckCircleFilled />;
  if (status === "failed") return <CloseCircleFilled />;
  if (status === "running") return <LoadingOutlined spin />;
  return <ClockCircleOutlined />;
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: "待执行",
    waiting: "等待中",
    paused: "已暂停",
    running: "进行中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  return labels[String(status || "queued").toLowerCase()] || String(status || "queued");
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

function formatRecord(value: Record<string, unknown>): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function shortText(value: string, max = 120): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}...` : text;
}

function shortTaskTitle(value: string, fallback: string): string {
  const text = shortText(value, 72);
  if (!text) return fallback;
  const focusIndex = text.indexOf("Focus as ");
  if (focusIndex > 0) return text.slice(0, focusIndex).trim();
  return text;
}
