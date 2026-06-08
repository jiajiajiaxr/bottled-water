import { describe, expect, it } from "vitest";
import type { Agent, ConversationWorkflow, Participant } from "../../types";
import {
  normalizeWorkflowAgentBindings,
  normalizeWorkflowForRun,
} from "./utils";
import { validateWorkflowDefinition } from "./validation";

function agent(id: string, name: string, type: string): Agent {
  return {
    id,
    name,
    type,
    version: "1",
    status: "online",
    description: `${name} handles ${type} work`,
    capabilities: [],
    provider: "test",
    is_official: false,
    response_latency_ms: 0,
    config: {},
  };
}

const agents = [
  agent("agent-frontend", "Frontend Worker", "frontend"),
  agent("agent-reviewer", "Reviewer", "reviewer"),
];

const participants: Participant[] = agents.map((item, index) => ({
  id: `p-${index}`,
  participant_type: "agent",
  agent_id: item.id,
  agent_name: item.name,
  agent_type: item.type,
}));

describe("normalizeWorkflowAgentBindings", () => {
  it("binds AI generated agent nodes that only have a node title/id", () => {
    const workflow: ConversationWorkflow = {
      mode: "ai_generated",
      output_mode: "independent_messages",
      nodes: [
        { id: "start", title: "任务启动", type: "start", role: "start" },
        {
          id: "agent-15198f4c",
          title: "Daily Chat Agent",
          type: "agent",
          role: "agent",
          status: "ready",
          meta: "Daily Chat Agent completed",
          config: {},
        },
        { id: "end", title: "任务结束", type: "end", role: "end" },
      ],
      edges: [
        ["start", "agent-15198f4c"],
        ["agent-15198f4c", "end"],
      ],
      settings: { enabled: true },
    };

    const bound = normalizeWorkflowAgentBindings(workflow, participants, agents);
    const runnable = normalizeWorkflowForRun(bound);
    const agentNode = runnable.nodes.find((node) => node.id === "agent-15198f4c");

    expect(agentNode?.agent_id).toBe("agent-frontend");
    expect(agentNode?.config?.agent_id).toBe("agent-frontend");
    expect(validateWorkflowDefinition(runnable).filter((issue) => issue.severity === "error")).toEqual([]);
  });
});
