import { describe, expect, it } from "vitest";

import type { AgentTask, ChatMessage, Conversation } from "../types";
import { deriveRunningConversationIds } from "./runningConversations";

function conversation(overrides: Partial<Conversation>): Conversation {
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

function runningIds({
  conversations,
  backgroundTasks = [],
  localRunningConversationIds = new Set<string>(),
  activeConversationId,
  activeMessages = [],
}: {
  conversations: Conversation[];
  backgroundTasks?: AgentTask[];
  localRunningConversationIds?: Set<string>;
  activeConversationId?: string;
  activeMessages?: ChatMessage[];
}) {
  return deriveRunningConversationIds({
    conversations,
    backgroundTasks,
    localRunningConversationIds,
    activeConversationId,
    activeMessages,
  });
}

describe("deriveRunningConversationIds", () => {
  it("uses backend generation_status as a running source", () => {
    const ids = runningIds({
      conversations: [conversation({ generation_status: "running" })],
    });

    expect(ids.has("conv-1")).toBe(true);
  });

  it("uses active_generation_id when generation_status is not present", () => {
    const ids = runningIds({
      conversations: [
        conversation({
          runtime: {
            active_generation_id: "gen-1",
            generations: [{ id: "gen-1", status: "running" }],
          },
        }),
      ],
    });

    expect(ids.has("conv-1")).toBe(true);
  });

  it("cleans stale local running state after cancellation", () => {
    const ids = runningIds({
      conversations: [
        conversation({
          generation_status: "cancelled",
          runtime: {
            active_generation_id: null,
            generations: [{ id: "gen-1", status: "cancelled" }],
          },
        }),
      ],
      localRunningConversationIds: new Set(["conv-1"]),
    });

    expect(ids.has("conv-1")).toBe(false);
  });

  it("ignores a stale active_generation_id when the generation is completed", () => {
    const ids = runningIds({
      conversations: [
        conversation({
          generation_status: "idle",
          runtime: {
            active_generation_id: "gen-1",
            generations: [{ id: "gen-1", status: "completed" }],
          },
        }),
      ],
    });

    expect(ids.has("conv-1")).toBe(false);
  });
});
