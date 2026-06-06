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
});
