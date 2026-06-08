import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RuntimeDecisionStrip } from "@/features/chat/components/ChatPanel/RuntimeDecisionStrip";
import type { Conversation } from "@/types";

function conversation(): Conversation {
  return {
    id: "conv-1",
    title: "group",
    chat_type: "group",
    participants: [
      {
        participant_type: "agent",
        agent_id: "72fbea2b-366e-4b86-8e08-47916dfa90e9",
        agent_name: "Daily Chat Agent",
      },
    ],
    updatedAt: "2026-06-05T00:00:00Z",
    pinned: false,
    archived: false,
    unread: 0,
    tags: [],
    lastMessage: "",
    generation_status: "running",
    runtime: {
      active_generation_id: "gen-1",
      generations: [
        {
          id: "gen-1",
          status: "running",
          agent_runs: [
            {
              agent_id: "72fbea2b-366e-4b86-8e08-47916dfa90e9",
              agent_name: "72fbea2b",
              status: "running",
            },
          ],
          decisions: [
            {
              round: 1,
              decision: "assign",
              target_agent_ids: ["72fbea2b-366e-4b86-8e08-47916dfa90e9"],
            },
          ],
        },
      ],
    },
  };
}

function progressConversation(): Conversation {
  return {
    ...conversation(),
    participants: [
      {
        participant_type: "agent",
        agent_id: "frontend",
        agent_name: "Frontend Worker",
      },
      {
        participant_type: "agent",
        agent_id: "backend",
        agent_name: "Backend Worker",
      },
    ],
    runtime: {
      active_generation_id: "gen-1",
      generations: [
        {
          id: "gen-1",
          status: "running",
          task_plan: [
            {
              id: "step-1",
              agent_id: "frontend",
              agent_name: "Frontend Worker",
              status: "completed",
              stage: 1,
              task: "Inspect dirty diff and build Web prototype",
            },
            {
              id: "step-2",
              agent_id: "backend",
              agent_name: "Backend Worker",
              status: "queued",
              stage: 1,
              task: "Run API checks with small tool loops",
            },
          ],
          agent_runs: [
            {
              agent_id: "frontend",
              agent_name: "Frontend Worker",
              status: "completed",
            },
            {
              agent_id: "backend",
              agent_name: "Backend Worker",
              status: "running",
            },
          ],
        },
      ],
    },
  };
}

function legacyRuntimeConversation(): Conversation {
  return {
    ...conversation(),
    participants: [
      {
        participant_type: "agent",
        agent_id: "frontend",
        agent_name: "Frontend Worker",
      },
      {
        participant_type: "agent",
        agent_id: "backend",
        agent_name: "Backend Worker",
      },
    ],
    runtime: {
      active_generation_id: "gen-legacy",
      generations: [
        {
          id: "gen-legacy",
          status: "running",
          agent_runs: [
            {
              agent_id: "frontend",
              agent_name: "Frontend Worker",
              status: "running",
              current_task: "请组织多智能体完成企业知识库问答 MVP，并在每个 Agent 下重复这条完整用户提示。",
            },
            {
              agent_id: "backend",
              agent_name: "Backend Worker",
              status: "queued",
              current_task: "请组织多智能体完成企业知识库问答 MVP，并在每个 Agent 下重复这条完整用户提示。",
            },
          ],
        },
      ],
    },
  };
}

describe("RuntimeDecisionStrip", () => {
  it("expands from the floating robot card and uses participant names", () => {
    render(<RuntimeDecisionStrip conversation={conversation()} />);

    expect(screen.queryByText(/Daily Chat Agent/)).toBeNull();
    const trigger = screen.getByLabelText("展开组织状态");
    fireEvent.pointerDown(trigger, { button: 0, pointerId: 1, clientX: 20, clientY: 20 });
    fireEvent.pointerUp(window, { pointerId: 1, clientX: 20, clientY: 20 });
    fireEvent.click(trigger);

    expect(screen.getAllByText(/Daily Chat Agent/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/72fbea2b · running/)).toBeNull();
  });

  it("shows a task progress list for multi-agent organization", () => {
    render(<RuntimeDecisionStrip conversation={progressConversation()} />);

    fireEvent.click(screen.getByLabelText("展开组织状态"));

    expect(screen.getByText("进度")).toBeInTheDocument();
    expect(screen.getByText("Inspect dirty diff and build Web prototype")).toBeInTheDocument();
    expect(screen.getByText("Run API checks with small tool loops")).toBeInTheDocument();
    expect(screen.getByText("Frontend Worker · 已完成")).toBeInTheDocument();
    expect(screen.getByText("Backend Worker · 进行中")).toBeInTheDocument();
  });

  it("falls back to agent run progress when scheduler plan is absent", () => {
    render(<RuntimeDecisionStrip conversation={legacyRuntimeConversation()} />);

    fireEvent.click(screen.getByLabelText("展开组织状态"));

    expect(screen.getByText("进度")).toBeInTheDocument();
    expect(screen.queryByText(/企业知识库问答 MVP/)).toBeNull();
    expect(screen.getByText("Frontend Worker · 进行中")).toBeInTheDocument();
    expect(screen.getByText("Backend Worker · 待执行")).toBeInTheDocument();
  });
});
