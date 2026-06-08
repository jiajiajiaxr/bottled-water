import { describe, expect, it } from "vitest";

import type { Conversation } from "../types";
import { applyRuntimeEvent } from "./runtimeEvents";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: "conv-1",
    title: "会话",
    participants: [],
    updatedAt: "2026-06-04T00:00:00Z",
    pinned: false,
    archived: false,
    unread: 0,
    tags: [],
    lastMessage: "",
    ...overrides,
  };
}

describe("applyRuntimeEvent", () => {
  it("records scheduler decisions in the active generation", () => {
    const patch = applyRuntimeEvent(conversation(), "scheduler.decision", {
      generation_id: "gen-1",
      round: 2,
      decision: {
        decision_type: "assign",
        target_agent_id: "agent-frontend",
        task_description: "实现页面",
        rationale: "前端任务交给前端 Agent",
      },
    });

    const generation = patch.runtime?.generations?.[0];
    expect(patch.generation_status).toBe("running");
    expect(patch.runtime?.active_generation_id).toBe("gen-1");
    expect(generation?.decisions?.[0]).toMatchObject({
      round: 2,
      decision: "assign",
      target: "agent-frontend",
    });
  });

  it("records scheduler plan and summary events", () => {
    const plan = [
      {
        id: "auto-1",
        agent_id: "agent-frontend",
        agent_name: "Frontend Worker",
        status: "queued",
        task: "build ui",
      },
    ];
    const planned = applyRuntimeEvent(conversation(), "scheduler.plan", {
      generation_id: "gen-1",
      plan,
    });
    const summarized = applyRuntimeEvent(
      conversation({ runtime: planned.runtime }),
      "scheduler.summary",
      {
        status: "completed",
        task: "build ui",
        plan: [{ ...plan[0], status: "completed", output_preview: "ui done" }],
        completed_agent_ids: ["agent-frontend"],
        final_answer: "Frontend Worker: ui done",
      },
    );

    const generation = summarized.runtime?.generations?.[0];
    expect(generation?.task_plan?.[0]).toMatchObject({
      agent_id: "agent-frontend",
      status: "completed",
    });
    expect(generation?.summary).toMatchObject({
      status: "completed",
      final_answer: "Frontend Worker: ui done",
    });
    expect(generation?.summaries).toHaveLength(1);
  });

  it("records legacy control scheduling decisions in the active generation", () => {
    const patch = applyRuntimeEvent(conversation(), "control.scheduling_decision", {
      generation_id: "gen-1",
      round: 1,
      decision: "assign",
      target: "deploy-agent",
      task: "reply to deploy mention",
      rationale: "Deploy Agent is the mentioned participant",
    });

    const generation = patch.runtime?.generations?.[0];
    expect(patch.generation_status).toBe("running");
    expect(generation?.decisions?.[0]).toMatchObject({
      round: 1,
      decision: "assign",
      target: "deploy-agent",
      task: "reply to deploy mention",
    });
  });

  it("updates agent runs from nested agent reports", () => {
    const base = conversation({
      runtime: {
        active_generation_id: "gen-1",
        generations: [{ id: "gen-1", status: "running" }],
      },
    });

    const patch = applyRuntimeEvent(base, "agent.report", {
      report: {
        agent_id: "agent-backend",
        state: "completed",
        rationale: "接口已完成",
      },
      input: {
        user_request: "build api",
        assigned_task: "implement endpoint",
      },
      work_product: "生成了 API 方案",
      output: {
        work_product: "生成了 API 方案",
        tool_events: [{ round: 1, results: [{ tool: "api.probe" }] }],
      },
      tool_events: [{ round: 1, results: [{ tool: "api.probe" }] }],
    });

    const run = patch.runtime?.generations?.[0].agent_runs?.[0];
    expect(run).toMatchObject({
      agent_id: "agent-backend",
      status: "completed",
      output_preview: "生成了 API 方案",
      rationale: "接口已完成",
      input: {
        user_request: "build api",
      },
      output: {
        work_product: "生成了 API 方案",
      },
      tool_count: 1,
    });
  });

  it("copies scheduler decision summaries", () => {
    const patch = applyRuntimeEvent(conversation(), "scheduler.decision", {
      generation_id: "gen-1",
      round: 1,
      plan: [{ agent_id: "agent-frontend", status: "running" }],
      summary: {
        status: "partial",
        task: "build ui",
        pending_agent_ids: ["agent-frontend"],
      },
      decision: {
        decision_type: "wait",
        target_agent_ids: ["agent-frontend"],
      },
    });

    const generation = patch.runtime?.generations?.[0];
    expect(generation?.task_plan?.[0]).toMatchObject({
      agent_id: "agent-frontend",
    });
    expect(generation?.summary?.status).toBe("partial");
    expect(generation?.decisions?.[0].summary?.pending_agent_ids).toEqual(["agent-frontend"]);
  });

  it("clears the active generation on cancellation", () => {
    const patch = applyRuntimeEvent(
      conversation({
        runtime: {
          active_generation_id: "gen-1",
          generations: [{ id: "gen-1", status: "running" }],
        },
      }),
      "control.cancel",
      {},
    );

    expect(patch.runtime?.active_generation_id).toBeNull();
    expect(patch.runtime?.generations?.[0].status).toBe("cancelled");
    expect(patch.generation_status).toBe("cancelled");
  });

  it("treats generation_finished as a global completion event", () => {
    const patch = applyRuntimeEvent(
      conversation({
        generation_status: "running",
        runtime: {
          active_generation_id: "gen-1",
          generations: [{ id: "gen-1", status: "running" }],
        },
      }),
      "generation_finished",
      { conversation_id: "conv-1" },
    );

    expect(patch.runtime?.active_generation_id).toBeNull();
    expect(patch.runtime?.generations?.[0].status).toBe("completed");
    expect(patch.generation_status).toBe("idle");
  });

  it("settles running agent runs when a generation completes", () => {
    const patch = applyRuntimeEvent(
      conversation({
        generation_status: "running",
        runtime: {
          active_generation_id: "gen-1",
          generations: [
            {
              id: "gen-1",
              status: "running",
              agent_runs: [
                { agent_id: "team_leader", agent_name: "Team Leader Scheduler", status: "running" },
                { agent_id: "agent-backend", agent_name: "Backend Worker", status: "ready" },
                { agent_id: "agent-daily", agent_name: "Daily Chat Agent", status: "completed" },
              ],
            },
          ],
        },
      }),
      "system.session_completed",
      { conversation_id: "conv-1" },
    );

    const runs = patch.runtime?.generations?.[0].agent_runs || [];
    expect(runs.find((item) => item.agent_id === "team_leader")?.status).toBe("completed");
    expect(runs.find((item) => item.agent_id === "agent-backend")?.status).toBe("ready");
  });
});
