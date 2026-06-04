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
  running: "processing",
  paused: "warning",
  waiting: "warning",
  completed: "success",
  failed: "error",
  cancelled: "default",
};

export function RuntimeDecisionStrip({ conversation }: { conversation?: Conversation }) {
  const generation = latestGeneration(conversation);
  if (!generation) return null;

  const decision = latestDecision(generation);
  const agentRuns = generation.agent_runs || [];
  const isVisible =
    decision ||
    agentRuns.some((item) => item.status && item.status !== "queued") ||
    generation.status === "running";
  if (!isVisible) return null;

  return (
    <div className="runtime-decision-strip" data-testid="runtime-decision-strip">
      <Space size={[8, 8]} wrap>
        <Tag color={generation.status === "running" ? "processing" : "default"}>
          调度 {generation.status || "idle"}
        </Tag>
        {decision && <DecisionTag decision={decision} />}
        {agentRuns.slice(0, 5).map((run) => (
          <AgentRunTag key={run.agent_id} run={run} />
        ))}
        {agentRuns.length > 5 && <Text type="secondary">等 {agentRuns.length} 个 Agent</Text>}
      </Space>
    </div>
  );
}

function DecisionTag({ decision }: { decision: ConversationRuntimeDecision }) {
  const label = [
    decision.round ? `第 ${decision.round} 轮` : "",
    decision.decision || "wait",
    decision.target ? `→ ${decision.target}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Tooltip title={decision.rationale || decision.task || "Team Leader 调度决策"}>
      <Tag color="blue">{label}</Tag>
    </Tooltip>
  );
}

function AgentRunTag({ run }: { run: ConversationRuntimeAgentRun }) {
  const status = String(run.status || "queued").toLowerCase();
  const name = run.agent_name || run.agent_id.slice(0, 8);
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

function latestGeneration(conversation?: Conversation): ConversationRuntimeGeneration | undefined {
  const generations = conversation?.runtime?.generations || [];
  return generations.length ? generations[generations.length - 1] : undefined;
}

function latestDecision(generation: ConversationRuntimeGeneration): ConversationRuntimeDecision | undefined {
  const decisions = generation.decisions || [];
  return decisions.length ? decisions[decisions.length - 1] : undefined;
}
