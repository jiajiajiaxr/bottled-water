import { describe, expect, it } from "vitest";
import { deriveRunningConversationIds } from "../src/lib/runningConversations";
import type { AgentTask, ChatMessage, Conversation } from "../src/types";

describe("running conversation derivation", () => {
  it("does not mark a refreshed conversation as running without active backend or message signals", () => {
    const running = deriveRunningConversationIds({
      conversations: [conversation("conversation-1")],
      backgroundTasks: [task("conversation-1", "COMPLETED")],
      localRunningConversationIds: new Set(),
      activeConversationId: "conversation-1",
      activeMessages: [message("conversation-1", "completed")],
    });

    expect(running.has("conversation-1")).toBe(false);
  });

  it("keeps group chat running while any task or active message is streaming", () => {
    const running = deriveRunningConversationIds({
      conversations: [conversation("group-1")],
      backgroundTasks: [task("group-1", "EXECUTING")],
      localRunningConversationIds: new Set(),
      activeConversationId: "group-1",
      activeMessages: [message("group-1", "streaming")],
    });

    expect(running.has("group-1")).toBe(true);
  });

  it("ignores stale local ids for conversations no longer in the sidebar", () => {
    const running = deriveRunningConversationIds({
      conversations: [conversation("conversation-1")],
      backgroundTasks: [],
      localRunningConversationIds: new Set(["missing-conversation"]),
      activeConversationId: "conversation-1",
      activeMessages: [],
    });

    expect([...running]).toEqual([]);
  });
});

function conversation(id: string): Conversation {
  return {
    id,
    title: id,
    participants: [],
    updatedAt: new Date().toISOString(),
    pinned: false,
    archived: false,
    unread: 0,
    tags: [],
    lastMessage: "final",
  };
}

function task(conversationId: string, status: string): AgentTask {
  return {
    id: `task-${conversationId}`,
    conversation_id: conversationId,
    title: "task",
    status,
  };
}

function message(conversationId: string, status: string): ChatMessage {
  return {
    id: `message-${conversationId}`,
    conversationId,
    role: "assistant",
    kind: "text",
    author: "Agent",
    content: "done",
    createdAt: new Date().toISOString(),
    status,
    streamState: status === "streaming" ? "streaming" : "done",
  };
}
