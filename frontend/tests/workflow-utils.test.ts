import { describe, expect, it } from "vitest";
import { normalizeWorkflowForRun } from "../src/features/workflow/utils";
import { workflowNodeType } from "../src/lib/workflow";
import { validateWorkflowDefinition } from "../src/features/workflow/validation";
import type { ConversationWorkflow } from "../src/types";

describe("workflow run normalization", () => {
  it("uses config.agent_id for agent nodes before validation/run", () => {
    const workflow: ConversationWorkflow = {
      mode: "canvas",
      nodes: [
        { id: "start", title: "Start", type: "start" },
        {
          id: "agent-step",
          title: "undefined",
          type: "agent",
          config: { agent_id: "agent-1" },
        },
        { id: "end", title: "End", type: "end" },
      ],
      edges: [
        ["start", "agent-step"],
        ["agent-step", "end"],
      ],
    };

    const normalized = normalizeWorkflowForRun(workflow);
    const agent = normalized.nodes[1];

    expect(agent.title).toBe("agent-step");
    expect(agent.agent_id).toBe("agent-1");
    expect(agent.config?.agent_id).toBe("agent-1");
    expect(validateWorkflowDefinition(normalized).filter((issue) => issue.severity === "error")).toEqual([]);
  });

  it("keeps legacy id-only start and end nodes runnable", () => {
    const workflow: ConversationWorkflow = {
      mode: "canvas",
      nodes: [
        { id: "start", title: "接收群聊输入" },
        {
          id: "agent-step",
          title: "Daily Chat Agent",
          config: { agent_id: "agent-1" },
        },
        { id: "end", title: "最终回复" },
      ],
      edges: [
        ["start", "agent-step"],
        ["agent-step", "end"],
      ],
    };

    expect(workflowNodeType(workflow.nodes[0])).toBe("start");
    expect(workflowNodeType(workflow.nodes[2])).toBe("end");

    const normalized = normalizeWorkflowForRun(workflow);

    expect(normalized.nodes[0]).toMatchObject({ type: "start", role: "start" });
    expect(normalized.nodes[2]).toMatchObject({ type: "end", role: "end" });
    expect(validateWorkflowDefinition(normalized).filter((issue) => issue.severity === "error")).toEqual([]);
  });
});
