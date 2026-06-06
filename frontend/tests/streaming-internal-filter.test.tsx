import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { makeMessage } from "../src/lib";
import { useStreamingMessages } from "../src/hooks/useStreamingMessages";
import { useConversationStore, useMessageStore } from "../src/store";

beforeEach(() => {
  useMessageStore.getState().setMessages([]);
  useMessageStore.getState().clearMessageCache();
  useConversationStore.setState({
    conversations: [],
    activeId: undefined,
    activeConversation: undefined,
    localRunningConversationIds: new Set(),
  });
});

describe("useStreamingMessages internal block filtering", () => {
  it("filters status_report fragments from streamed thinking text", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });

    act(() => {
      result.current.streamHandlers.onThinking?.("agent-1", "visible thinking\n``");
    });

    expect(result.current.streamingMessages.get("agent-1")?.thinking).toBe(
      "visible thinking",
    );

    act(() => {
      result.current.streamHandlers.onThinking?.(
        "agent-1",
        '`status_report\n{"state":"completed"}\n```\nvisible conclusion',
      );
    });

    expect(result.current.streamingMessages.get("agent-1")?.thinking).toBe(
      "visible thinking\nvisible conclusion",
    );
  });

  it("filters status_report fragments from streamed answer text", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });

    act(() => {
      result.current.streamHandlers.onDelta?.("可见回答\n``", {
        agent_id: "agent-1",
        agent_message_id: "message-1",
      });
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "可见回答",
    );

    act(() => {
      result.current.streamHandlers.onDelta?.(
        '`status_report\n{"state":"completed","rationale":"done"}\n```\n继续说明',
        {
          agent_id: "agent-1",
          agent_message_id: "message-1",
        },
      );
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "可见回答\n继续说明",
    );
  });
  it("keeps bare opening fences hidden until status_report body is removed", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });

    act(() => {
      result.current.streamHandlers.onDelta?.("visible answer\n```\n", {
        agent_id: "agent-1",
        agent_message_id: "message-1",
      });
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "visible answer",
    );

    act(() => {
      result.current.streamHandlers.onDelta?.(
        'status_report\n{"state":"completed","will":"complete"}\n```\nfinal',
        {
          agent_id: "agent-1",
          agent_message_id: "message-1",
        },
      );
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "visible answer\nfinal",
    );
  });

  it("hides local streaming bubbles after the persisted agent message arrives", () => {
    useConversationStore.getState().setConversations([
      {
        id: "conversation-1",
        chat_type: "single",
        title: "Daily Chat Agent",
        participants: [
          {
            participant_type: "agent",
            agent_id: "agent-1",
            agent_name: "Daily Chat Agent",
          },
        ],
        updatedAt: "2026-06-06T00:00:00Z",
        pinned: false,
        archived: false,
        unread: 0,
        tags: [],
        lastMessage: "",
      },
    ]);
    useConversationStore.getState().setActiveId("conversation-1");

    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onToken?.("agent-1", "我可以帮你", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "我可以帮你",
    );

    const persisted = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "text",
      author: "Daily Chat Agent",
      content: "我可以帮你",
      rawContent: { agent_id: "agent-1" },
      streamState: "done",
      status: "completed",
      state: "active",
    });
    persisted.id = "persisted-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(persisted);
    });

    expect(useMessageStore.getState().historyMessages).toEqual([persisted]);
    expect(result.current.streamingMessages.size).toBe(0);
    expect(result.current.displayOrder).toEqual([]);
  });
});
