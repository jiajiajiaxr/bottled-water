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
  const generation = latestGeneration(conversation);
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

  return (
    <div className="runtime-decision-strip" data-testid="runtime-decision-strip">
      <Space size={[8, 8]} wrap>
        <Tag color={status === "running" ? "processing" : "default"}>
          {modeLabel(conversation)} · {status}
        </Tag>
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
