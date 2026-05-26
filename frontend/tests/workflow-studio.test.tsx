import React from "react";
import { App as AntApp } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import { WorkflowStudioPage } from "../src/pages/WorkflowStudioPage";
import type {
  Agent,
  Conversation,
  ConversationWorkflow,
  User,
  WorkflowRun,
} from "../src/types";

vi.mock("../src/api", () => ({
  api: {
    agents: vi.fn(),
    conversations: vi.fn(),
    conversationWorkflow: vi.fn(),
    workflowRuns: vi.fn(),
    tools: vi.fn(),
    skills: vi.fn(),
    mcpServers: vi.fn(),
    saveConversationWorkflow: vi.fn(),
    generateConversationWorkflow: vi.fn(),
    startWorkflowRun: vi.fn(),
  },
}));

vi.mock("../src/features/chat/components/drawers/WorkflowCanvas", () => ({
  WorkflowCanvas: ({
    workflow,
    onNodeClick,
  }: {
    workflow: ConversationWorkflow;
    onNodeClick: (node: ConversationWorkflow["nodes"][number]) => void;
  }) => (
    <div data-testid="workflow-canvas">
      {workflow.nodes.map((node) => (
        <button key={node.id} type="button" onClick={() => onNodeClick(node)}>
          {node.title}
        </button>
      ))}
    </div>
  ),
}));

const user: User = {
  id: "u1",
  name: "演示用户",
  role: "demo",
};

const conversation: Conversation = {
  id: "c1",
  workspace_id: "w1",
  chat_type: "group",
  title: "Demo 群聊",
  participants: [
    { id: "p1", participant_type: "agent", agent_id: "a1", agent_name: "前端" },
  ],
  updatedAt: "2026-05-26T00:00:00Z",
  pinned: false,
  archived: false,
  unread: 0,
  tags: [],
  category: "Default",
};

const agent: Agent = {
  id: "a1",
  name: "Frontend Worker",
  type: "frontend",
  version: "1.0.0",
  capabilities: [],
  description: "前端开发",
  status: "online",
  provider: "official",
  is_official: true,
  response_latency_ms: 0,
  config: {},
};

const workflow: ConversationWorkflow = {
  conversation_id: "c1",
  mode: "all_agents_independent",
  output_mode: "independent_messages",
  settings: { enabled: true, published: false },
  nodes: [
    {
      id: "start",
      title: "Start",
      type: "start",
      status: "queued",
      position: { x: 0, y: 0 },
    },
    {
      id: "agent_1",
      title: "Frontend Worker",
      type: "agent",
      agent_id: "a1",
      status: "queued",
      position: { x: 260, y: 0 },
    },
    {
      id: "end",
      title: "End",
      type: "end",
      status: "queued",
      position: { x: 520, y: 0 },
    },
  ],
  edges: [
    ["start", "agent_1"],
    ["agent_1", "end"],
  ],
};

const generatedWorkflow: ConversationWorkflow = {
  ...workflow,
  nodes: workflow.nodes.map((node) =>
    node.id === "agent_1" ? { ...node, title: "Generated Agent" } : node,
  ),
};

const run: WorkflowRun = {
  id: "run1",
  conversation_id: "c1",
  status: "running",
  mode: "all_agents_independent",
  workflow_snapshot: workflow,
  node_states: [{ ...workflow.nodes[1], status: "running", progress: 30 }],
  edge_states: [{ from: "start", to: "agent_1", status: "completed" }],
  events: [{ type: "node_started", node_id: "agent_1" }],
  progress: 30,
};

function renderWorkflowStudio() {
  return render(
    <AntApp>
      <MemoryRouter
        initialEntries={["/workspaces/w1/conversations/c1/workflow"]}
      >
        <Routes>
          <Route
            path="/workspaces/:workspaceId/conversations/:conversationId/workflow"
            element={<WorkflowStudioPage user={user} />}
          />
          <Route path="/app/:workspaceId/c/:conversationId" element={<div>群聊页</div>} />
        </Routes>
      </MemoryRouter>
    </AntApp>,
  );
}

describe("WorkflowStudioPage", () => {
  beforeEach(() => {
    vi.mocked(api.conversations).mockResolvedValue([conversation]);
    vi.mocked(api.agents).mockResolvedValue([agent]);
    vi.mocked(api.conversationWorkflow).mockResolvedValue(workflow);
    vi.mocked(api.workflowRuns).mockResolvedValue([]);
    vi.mocked(api.tools).mockResolvedValue([]);
    vi.mocked(api.skills).mockResolvedValue([]);
    vi.mocked(api.mcpServers).mockResolvedValue([]);
    vi.mocked(api.saveConversationWorkflow).mockResolvedValue(workflow);
    vi.mocked(api.generateConversationWorkflow).mockResolvedValue(generatedWorkflow);
    vi.mocked(api.startWorkflowRun).mockResolvedValue(run);
  });

  it("loads the routed canvas and returns to the conversation", async () => {
    renderWorkflowStudio();

    expect(await screen.findByText("Demo 群聊")).toBeInTheDocument();
    expect(screen.getByTestId("workflow-canvas")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("workflow-back"));
    expect(await screen.findByText("群聊页")).toBeInTheDocument();
  });

  it("saves, generates and starts a workflow run", async () => {
    renderWorkflowStudio();

    await screen.findByText("Demo 群聊");
    fireEvent.click(screen.getByRole("button", { name: /保存/ }));
    await waitFor(() => {
      expect(api.saveConversationWorkflow).toHaveBeenCalledWith("c1", expect.any(Object));
    });

    fireEvent.click(screen.getByRole("button", { name: /AI 生成/ }));
    expect(await screen.findByText("Generated Agent")).toBeInTheDocument();
    expect(api.generateConversationWorkflow).toHaveBeenCalledWith("c1", "");

    fireEvent.click(screen.getByRole("button", { name: /运行/ }));
    await waitFor(() => {
      expect(api.startWorkflowRun).toHaveBeenCalledWith("c1", expect.any(Object));
    });
    expect(await screen.findByText("running")).toBeInTheDocument();
  });
});
