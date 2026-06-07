import { beforeEach, describe, expect, it } from "vitest";
import { useMessageStore } from "../src/store";
import type { ChatMessage } from "../src/types";

function message(
  id: string,
  conversationId: string,
  content: string,
): ChatMessage {
  return {
    id,
    conversationId,
    role: "assistant",
    kind: "text",
    author: "Daily Chat Agent",
    content,
    createdAt: "2026-06-07T00:00:00.000Z",
    streamState: "done",
    state: "active",
  };
}

beforeEach(() => {
  useMessageStore.getState().clearMessages();
  useMessageStore.getState().clearMessageCache();
});

describe("message store conversation isolation", () => {
  it("does not carry old conversation history into a new conversation", () => {
    const oldMessage = message("old-message", "conversation-old", "旧会话消息");
    const newMessage = message("new-message", "conversation-new", "新会话消息");

    useMessageStore
      .getState()
      .setMessagesForConversation("conversation-old", [oldMessage]);
    useMessageStore
      .getState()
      .setMessagesForConversation("conversation-new", []);
    useMessageStore
      .getState()
      .updateMessagesForConversation("conversation-new", (prev) => [
        ...prev,
        newMessage,
      ]);

    const state = useMessageStore.getState();
    expect(state.historyConversationId).toBe("conversation-new");
    expect(state.historyMessages).toEqual([newMessage]);
    expect(state.getCachedMessages("conversation-old")).toEqual([oldMessage]);
    expect(state.getCachedMessages("conversation-new")).toEqual([newMessage]);
  });

  it("filters mismatched messages when setting a conversation bucket", () => {
    const oldMessage = message("old-message", "conversation-old", "旧会话消息");
    const newMessage = message("new-message", "conversation-new", "新会话消息");

    useMessageStore
      .getState()
      .setMessagesForConversation("conversation-new", [oldMessage, newMessage]);

    const state = useMessageStore.getState();
    expect(state.historyConversationId).toBe("conversation-new");
    expect(state.historyMessages).toEqual([newMessage]);
    expect(state.getCachedMessages("conversation-new")).toEqual([newMessage]);
  });

  it("keeps the visible history on the active conversation when an old conversation updates late", () => {
    const oldMessage = message("old-message", "conversation-old", "旧会话消息");
    const lateOldMessage = message(
      "late-old-message",
      "conversation-old",
      "旧会话迟到消息",
    );
    const newMessage = message("new-message", "conversation-new", "新会话消息");

    useMessageStore
      .getState()
      .setMessagesForConversation("conversation-old", [oldMessage]);
    useMessageStore
      .getState()
      .setMessagesForConversation("conversation-new", [newMessage]);
    useMessageStore
      .getState()
      .updateMessagesForConversation("conversation-old", (prev) => [
        ...prev,
        lateOldMessage,
      ]);

    const state = useMessageStore.getState();
    expect(state.historyConversationId).toBe("conversation-new");
    expect(state.historyMessages).toEqual([newMessage]);
    expect(state.getCachedMessages("conversation-old")).toEqual([
      oldMessage,
      lateOldMessage,
    ]);
  });
});
