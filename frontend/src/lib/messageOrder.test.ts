import { describe, expect, it } from "vitest";
import { mergeVisibleMessagesForDisplay } from "./messageOrder";
import type { ChatMessage } from "@/types";

function message(
  id: string,
  role: ChatMessage["role"],
  createdAt: string,
  content = id,
): ChatMessage {
  return {
    id,
    conversationId: "conversation-1",
    role,
    kind: "text",
    author: role === "user" ? "User" : "Agent",
    content,
    createdAt,
    state: "active",
  };
}

describe("mergeVisibleMessagesForDisplay", () => {
  it("keeps an in-flight assistant reply before later user interjections", () => {
    const history = [
      message("user-1", "user", "2026-06-07T10:00:00.000Z"),
      message("user-2", "user", "2026-06-07T10:02:00.000Z"),
    ];
    const streaming = new Map([
      ["agent-1", message("agent-1", "assistant", "2026-06-07T10:01:00.000Z")],
    ]);

    const merged = mergeVisibleMessagesForDisplay(history, streaming, ["agent-1"]);

    expect(merged.map((item) => item.id)).toEqual([
      "user-1",
      "agent-1",
      "user-2",
    ]);
  });

  it("anchors a live assistant reply after the user message that triggered it", () => {
    const history = [
      message("user-1", "user", "2026-06-07T10:00:00.000Z"),
      message("user-2", "user", "2026-06-07T09:59:00.000Z"),
    ];
    const streamingMessage = {
      ...message("agent-1", "assistant", "2026-06-07T09:58:00.000Z"),
      rawContent: {
        _streamHistoryBoundaryIds: ["user-1"],
      },
    };
    const streaming = new Map([["agent-1", streamingMessage]]);

    const merged = mergeVisibleMessagesForDisplay(history, streaming, ["agent-1"]);

    expect(merged.map((item) => item.id)).toEqual([
      "user-2",
      "user-1",
      "agent-1",
    ]);
  });

  it("keeps a persisted assistant reply after its triggering user when server time is earlier", () => {
    const persistedAssistant = {
      ...message("agent-1", "assistant", "2026-06-07T09:58:00.000Z"),
      rawContent: {
        _streamHistoryBoundaryIds: ["user-1"],
      },
    };
    const history = [
      persistedAssistant,
      message("user-1", "user", "2026-06-07T10:00:00.000Z"),
    ];

    const merged = mergeVisibleMessagesForDisplay(history, new Map(), []);

    expect(merged.map((item) => item.id)).toEqual(["user-1", "agent-1"]);
  });

  it("keeps a persisted assistant reply at its stream position when completion time is later", () => {
    const persistedAssistant = {
      ...message("agent-1", "assistant", "2026-06-07T10:03:00.000Z"),
      rawContent: {
        _streamHistoryBoundaryIds: ["user-1"],
      },
    };
    const history = [
      message("user-1", "user", "2026-06-07T10:00:00.000Z"),
      message("user-2", "user", "2026-06-07T10:02:00.000Z"),
      persistedAssistant,
    ];

    const merged = mergeVisibleMessagesForDisplay(history, new Map(), []);

    expect(merged.map((item) => item.id)).toEqual([
      "user-1",
      "agent-1",
      "user-2",
    ]);
  });

  it("keeps the assistant anchored when the optimistic user id is replaced", () => {
    const persistedUser = {
      ...message("server-user-1", "user", "2026-06-07T10:05:00.000Z"),
      rawContent: {
        client_message_id: "client-1",
      },
      client_message_id: "client-1",
    };
    const streamingMessage = {
      ...message("agent-1", "assistant", "2026-06-07T09:58:00.000Z"),
      rawContent: {
        _streamHistoryBoundaryIds: ["local-user-1", "client-1"],
      },
    };
    const streaming = new Map([["agent-1", streamingMessage]]);

    const merged = mergeVisibleMessagesForDisplay(
      [persistedUser],
      streaming,
      ["agent-1"],
    );

    expect(merged.map((item) => item.id)).toEqual([
      "server-user-1",
      "agent-1",
    ]);
  });

  it("withholds an anchored stream until the triggering user message is visible", () => {
    const streamingMessage = {
      ...message("agent-1", "assistant", "2026-06-07T09:58:00.000Z"),
      rawContent: {
        _streamHistoryBoundaryIds: ["client-1"],
      },
    };
    const streaming = new Map([["agent-1", streamingMessage]]);

    const merged = mergeVisibleMessagesForDisplay([], streaming, ["agent-1"]);

    expect(merged).toEqual([]);
  });

  it("shows an anchored stream as soon as the triggering user message appears", () => {
    const user = {
      ...message("local-user-1", "user", "2026-06-07T10:00:00.000Z"),
      rawContent: {
        client_message_id: "client-1",
      },
      client_message_id: "client-1",
    };
    const streamingMessage = {
      ...message("agent-1", "assistant", "2026-06-07T09:58:00.000Z"),
      rawContent: {
        _streamHistoryBoundaryIds: ["client-1"],
      },
    };
    const streaming = new Map([["agent-1", streamingMessage]]);

    const merged = mergeVisibleMessagesForDisplay([user], streaming, ["agent-1"]);

    expect(merged.map((item) => item.id)).toEqual(["local-user-1", "agent-1"]);
  });

  it("sorts persisted history messages into the same visible timeline", () => {
    const history = [
      message("user-2", "user", "2026-06-07T10:02:00.000Z"),
      message("agent-1", "assistant", "2026-06-07T10:01:00.000Z"),
      message("user-1", "user", "2026-06-07T10:00:00.000Z"),
    ];

    const merged = mergeVisibleMessagesForDisplay(history, new Map(), []);

    expect(merged.map((item) => item.id)).toEqual([
      "user-1",
      "agent-1",
      "user-2",
    ]);
  });

  it("drops an active stream once the same message is represented by history", () => {
    const persisted = message(
      "agent-message-1",
      "assistant",
      "2026-06-07T10:01:00.000Z",
      "done",
    );
    const streamingMessage = {
      ...message("agent-message-1", "assistant", "2026-06-07T10:01:00.000Z"),
      streamState: "streaming" as const,
    };

    const merged = mergeVisibleMessagesForDisplay(
      [persisted],
      new Map([["agent-1", streamingMessage]]),
      ["agent-1"],
    );

    expect(merged).toHaveLength(1);
    expect(merged[0]?.content).toBe("done");
  });
});
