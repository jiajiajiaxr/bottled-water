import { describe, expect, it } from "vitest";
import {
  isSuccessfulToolRunnerMessage,
  isVisibleChatMessage,
} from "../src/lib/message";
import type { ChatMessage } from "../src/types";

describe("chat message visibility", () => {
  it("hides successful Tool Runner messages from the main chat", () => {
    const message = makeMessage({
      author: "Tool Runner",
      kind: "event",
      rawContent: {
        tool_name: "file.summarize",
        output: { status: "succeeded", summary: "done" },
      },
    });

    expect(isSuccessfulToolRunnerMessage(message)).toBe(true);
    expect(isVisibleChatMessage(message)).toBe(false);
  });

  it("keeps failed Tool Runner messages visible", () => {
    const message = makeMessage({
      author: "Tool Runner",
      kind: "event",
      rawContent: {
        tool_name: "file.summarize",
        output: { status: "failed", error: "parse failed" },
      },
    });

    expect(isSuccessfulToolRunnerMessage(message)).toBe(false);
    expect(isVisibleChatMessage(message)).toBe(true);
  });
});

function makeMessage(partial: Partial<ChatMessage>): ChatMessage {
  return {
    id: "message-1",
    conversationId: "conversation-1",
    role: "assistant",
    kind: "text",
    author: "Agent",
    content: "",
    createdAt: new Date().toISOString(),
    ...partial,
  };
}
