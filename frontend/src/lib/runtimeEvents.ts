import type {
  Conversation,
  ConversationRuntime,
  ConversationRuntimeAgentRun,
  ConversationRuntimeGeneration,
} from "../types";

export function applyRuntimeEvent(
  conversation: Conversation,
  event: string,
  payload: Record<string, unknown>,
): Partial<Conversation> {
  const runtime = ensureRuntime(conversation.runtime, payload);
  const generation = latestOrActiveGeneration(runtime);
  if (!generation) return {};

  generation.event_counts = {
    ...(generation.event_counts || {}),
    [event]: (generation.event_counts?.[event] || 0) + 1,
  };

  if (event === "scheduler.decision") {
    const decision = payload.decision as Record<string, unknown> | undefined;
    generation.decisions = [
      ...(generation.decisions || []),
      {
        round: numberOrUndefined(payload.round),
        decision: stringOrUndefined(decision?.action ?? decision?.decision_type ?? decision?.decision),
        target: stringOrUndefined(decision?.target_agent_id ?? payload.target),
        target_agent_ids: arrayOfStrings(decision?.target_agent_ids ?? payload.target_agent_ids),
        task: stringOrUndefined(decision?.task ?? decision?.task_description ?? payload.task),
        rationale: stringOrUndefined(decision?.rationale ?? payload.rationale),
        expected_outputs: arrayOfStrings(decision?.expected_outputs),
        requires_review: Boolean(decision?.requires_review ?? decision?.requires_verification),
        fallback_reason: stringOrUndefined(decision?.fallback_reason),
        created_at: new Date().toISOString(),
      },
    ].slice(-20);
  }

  if (event === "agent.state_changed") {
    const agentId = agentIdFromPayload(payload);
    if (agentId) {
      const run = upsertAgentRun(generation, agentId);
      run.agent_name = stringOrUndefined(payload.agent_name) || run.agent_name;
      run.status = stringOrUndefined(payload.state) || run.status;
      run.current_task = stringOrUndefined(payload.task) || run.current_task;
      if (run.status === "running") run.started_at ||= new Date().toISOString();
      if (["completed", "failed", "cancelled"].includes(String(run.status))) {
        run.completed_at ||= new Date().toISOString();
      }
      if (run.status === "failed") run.error = stringOrUndefined(payload.reason) || run.error;
    }
  }

  if (event === "agent.report") {
    const agentId = agentIdFromPayload(payload);
    const report = payload.report as Record<string, unknown> | undefined;
    if (agentId) {
      const run = upsertAgentRun(generation, agentId);
      run.agent_name =
        stringOrUndefined(payload.agent_name ?? report?.agent_name) || run.agent_name;
      run.status = stringOrUndefined(report?.state) || "completed";
      run.output_preview = stringOrUndefined(payload.work_product) || run.output_preview;
      run.rationale = stringOrUndefined(report?.rationale) || run.rationale;
      run.completed_at ||= new Date().toISOString();
    }
  }

  if (event === "agent.failed") {
    const agentId = agentIdFromPayload(payload);
    if (agentId) {
      const run = upsertAgentRun(generation, agentId);
      run.agent_name = stringOrUndefined(payload.agent_name) || run.agent_name;
      run.status = "failed";
      run.error = stringOrUndefined(payload.error) || "Agent failed";
      run.completed_at ||= new Date().toISOString();
    }
  }

  if (event === "control.watchdog_triggered") {
    const reason = stringOrUndefined(payload.reason) || "watchdog_triggered";
    generation.error = readableWatchdogReason(reason, payload);
    generation.status = "failed";
  }

  const terminalStatus = terminalStatusForEvent(event);
  if (terminalStatus) {
    generation.status = terminalStatus;
    generation.completed_at ||= new Date().toISOString();
    if (terminalStatus === "cancelled") generation.cancelled_at ||= generation.completed_at;
    settleAgentRuns(generation, terminalStatus);
    runtime.active_generation_id = null;
  }

  return {
    runtime,
    generation_status: runtime.active_generation_id
      ? "running"
      : terminalStatus === "completed"
        ? "idle"
        : terminalStatus || generation.status,
  };
}

function terminalStatusForEvent(event: string): "completed" | "failed" | "cancelled" | undefined {
  if (
    [
      "system.session_completed",
      "generation_finished",
      "generation:finished",
      "workflow_completed",
      "workflow:completed",
      "workflow:run_completed",
    ].includes(event)
  ) {
    return "completed";
  }
  if (
    [
      "system.session_cancelled",
      "generation:cancelled",
      "cancelled",
      "control.cancel",
      "workflow:cancelled",
      "workflow_cancelled",
    ].includes(event)
  ) {
    return "cancelled";
  }
  if (
    [
      "system.session_error",
      "generation:failed",
      "failed",
      "workflow:failed",
      "workflow_failed",
      "control.watchdog_triggered",
    ].includes(event)
  ) {
    return "failed";
  }
  return undefined;
}

function ensureRuntime(
  runtime: ConversationRuntime | undefined,
  payload: Record<string, unknown>,
): ConversationRuntime {
  const generations: ConversationRuntimeGeneration[] = (runtime?.generations || []).map((item) => ({
    ...item,
    decisions: item.decisions ? [...item.decisions] : undefined,
    agent_runs: item.agent_runs ? item.agent_runs.map((run) => ({ ...run })) : undefined,
    event_counts: item.event_counts ? { ...item.event_counts } : undefined,
  }));
  const next: ConversationRuntime = {
    active_generation_id: runtime?.active_generation_id,
    generations,
  };
  if (!next.active_generation_id && generations.length) {
    const latest = generations[generations.length - 1];
    if (!["completed", "failed", "cancelled", "canceled"].includes(String(latest.status || ""))) {
      next.active_generation_id = latest.id;
    }
  }
  if (!next.active_generation_id) {
    const id = stringOrUndefined(payload.generation_id ?? payload.session_id) || `live-${Date.now()}`;
    next.active_generation_id = id;
    generations.push({ id, status: "running", started_at: new Date().toISOString() });
  }
  return next;
}

function latestOrActiveGeneration(runtime: ConversationRuntime): ConversationRuntimeGeneration | undefined {
  const generations = runtime.generations || [];
  if (!generations.length) return undefined;
  return (
    generations.find((item) => item.id === runtime.active_generation_id) ||
    generations[generations.length - 1]
  );
}

function upsertAgentRun(generation: ConversationRuntimeGeneration, agentId: string): ConversationRuntimeAgentRun {
  const runs = [...(generation.agent_runs || [])];
  let run = runs.find((item) => item.agent_id === agentId);
  if (!run) {
    run = { agent_id: agentId, agent_name: agentId.slice(0, 8), status: "queued" };
    runs.push(run);
    generation.agent_runs = runs;
  }
  return run;
}

function readableWatchdogReason(reason: string, payload: Record<string, unknown>): string {
  const labels: Record<string, string> = {
    max_rounds_exceeded: "调度轮数超过上限",
    token_budget_exhausted: "Token 预算耗尽",
    deadlock_detected: "检测到无进展或死锁",
    timeout: "运行超时",
    decision_loop: "调度决策循环",
  };
  const label = labels[reason] || reason;
  const details = [
    numberOrUndefined(payload.rounds) ? `轮数 ${payload.rounds}` : "",
    numberOrUndefined(payload.elapsed_seconds) ? `耗时 ${Math.round(Number(payload.elapsed_seconds))}s` : "",
    numberOrUndefined(payload.max_seconds) ? `上限 ${payload.max_seconds}s` : "",
  ].filter(Boolean);
  return details.length ? `${label}（${details.join("，")}）` : label;
}

function settleAgentRuns(
  generation: ConversationRuntimeGeneration,
  terminalStatus: "completed" | "failed" | "cancelled",
) {
  const now = generation.completed_at || new Date().toISOString();
  generation.agent_runs = (generation.agent_runs || []).map((run) => {
    const status = String(run.status || "").toLowerCase();
    const isOpen = ["running", "waiting", "paused"].includes(status);
    const isPending = ["queued", "ready", "idle"].includes(status);
    if (terminalStatus === "completed") {
      return isOpen ? { ...run, status: "completed", completed_at: run.completed_at || now } : run;
    }
    if (isOpen || isPending) {
      return { ...run, status: terminalStatus, completed_at: run.completed_at || now };
    }
    return run;
  });
}

function agentIdFromPayload(payload: Record<string, unknown>): string | undefined {
  const report = payload.report as Record<string, unknown> | undefined;
  return stringOrUndefined(payload.agent_id ?? report?.agent_id);
}

function stringOrUndefined(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  return String(value);
}

function numberOrUndefined(value: unknown): number | undefined {
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item)).filter(Boolean)
    : [];
}
