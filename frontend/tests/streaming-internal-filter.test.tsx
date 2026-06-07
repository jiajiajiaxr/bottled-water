import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeMessage } from "../src/lib";
import { useStreamingMessages } from "../src/hooks/useStreamingMessages";
import { useConversationStore, useMessageStore } from "../src/store";

beforeEach(() => {
  vi.useFakeTimers();
  useMessageStore.getState().setMessages([]);
  useMessageStore.getState().clearMessageCache();
  useConversationStore.setState({
    conversations: [],
    activeId: undefined,
    activeConversation: undefined,
    localRunningConversationIds: new Set(),
  });
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
});

function flushTypewriter() {
  act(() => {
    vi.runAllTimers();
  });
}

function currentStream(result: {
  current: ReturnType<typeof useStreamingMessages>;
}) {
  const visibleKey = result.current.displayOrder[0];
  return visibleKey
    ? result.current.streamingMessages.get(visibleKey)
    : Array.from(result.current.streamingMessages.values())[0];
}

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
    flushTypewriter();

    expect(currentStream(result)?.thinking).toBe(
      "visible thinking",
    );

    act(() => {
      result.current.streamHandlers.onThinking?.(
        "agent-1",
        '`status_report\n{"state":"completed"}\n```\nvisible conclusion',
      );
    });
    flushTypewriter();

    expect(currentStream(result)?.thinking).toBe(
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

    expect(currentStream(result)?.content).toBe("可");
    flushTypewriter();

    expect(currentStream(result)?.content).toBe(
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
    flushTypewriter();

    expect(currentStream(result)?.content).toBe(
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

    expect(currentStream(result)?.content).toBe("v");
    flushTypewriter();

    expect(currentStream(result)?.content).toBe(
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
    flushTypewriter();

    expect(currentStream(result)?.content).toBe(
      "visible answer\nfinal",
    );
  });

  it("merges token events without message ids into an existing message_start bubble", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        conversation_id: "conversation-1",
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });

    act(() => {
      result.current.streamHandlers.onToken?.("agent-1", "你好呀", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });

    expect(result.current.displayOrder).toHaveLength(1);
    const visibleKey = result.current.displayOrder[0];
    expect(result.current.streamingMessages.get(visibleKey)?.id).toBe("message-1");
    expect(result.current.streamingMessages.get(visibleKey)?.content).toBe("你");
    flushTypewriter();
    expect(result.current.streamingMessages.get(visibleKey)?.content).toBe("你好呀");
  });

  it("keeps explicit stream ids separate for repeated same-agent assignments", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        conversation_id: "conversation-1",
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
      result.current.streamHandlers.onToken?.("agent-1", "first", {
        conversation_id: "conversation-1",
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });
    flushTypewriter();

    act(() => {
      result.current.streamHandlers.onToken?.("agent-1", "second", {
        conversation_id: "conversation-1",
        agent_id: "agent-1",
        agent_message_id: "message-2",
        agent_name: "Daily Chat Agent",
      });
    });
    flushTypewriter();

    expect(result.current.displayOrder).toEqual(["message-1", "message-2"]);
    expect(result.current.streamingMessages.get("message-1")?.content).toBe("first");
    expect(result.current.streamingMessages.get("message-2")?.content).toBe("second");
  });

  it("drains thinking before showing answer content", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    const payload = {
      conversation_id: "conversation-1",
      agent_id: "agent-1",
      agent_message_id: "message-1",
      agent_name: "Daily Chat Agent",
      thinking_enabled: true,
    };

    act(() => {
      result.current.streamHandlers.onMessageStart(payload);
      result.current.streamHandlers.onThinking?.("agent-1", "先完成思考", payload);
      result.current.streamHandlers.onToken?.("agent-1", "再输出正文", payload);
    });

    expect(currentStream(result)?.thinking).toBe("先");
    expect(currentStream(result)?.content).toBe("");

    flushTypewriter();

    expect(currentStream(result)?.thinking).toBe("先完成思考");
    expect(currentStream(result)?.content).toBe("再输出正文");
  });

  it("streams the persisted final suffix before committing history", () => {
    useConversationStore.getState().setActiveId("conversation-1");
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onToken?.("agent-1", "第一句。", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });
    flushTypewriter();

    expect(currentStream(result)?.content).toBe("第一句。");

    const persisted = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "text",
      author: "Daily Chat Agent",
      content: "第一句。第二句。",
      rawContent: { agent_id: "agent-1" },
      streamState: "done",
      status: "completed",
      state: "active",
    });
    persisted.id = "persisted-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(persisted);
    });

    expect(result.current.streamingMessages.size).toBe(1);
    expect(useMessageStore.getState().historyMessages).toEqual([]);
    expect(currentStream(result)?.content).toBe("第一句。第");

    flushTypewriter();

    expect(result.current.streamingMessages.size).toBe(0);
    expect(useMessageStore.getState().historyMessages).toEqual([persisted]);
  });

  it("does not append a mismatched persisted final message into the live token queue", () => {
    useConversationStore.getState().setActiveId("conversation-1");
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onToken?.("agent-1", "流式前缀", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });
    flushTypewriter();

    const persisted = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "text",
      author: "Daily Chat Agent",
      content: "完全不同的最终文本",
      rawContent: { agent_id: "agent-1" },
      streamState: "done",
      status: "completed",
      state: "active",
    });
    persisted.id = "persisted-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(persisted);
    });

    expect(result.current.streamingMessages.size).toBe(0);
    expect(useMessageStore.getState().historyMessages).toEqual([persisted]);
  });

  it("does not let an older assistant history message hide the next turn stream", () => {
    useConversationStore.getState().setActiveId("conversation-1");
    useMessageStore.getState().setMessagesForConversation("conversation-1", [
      {
        id: "previous-agent-message",
        conversationId: "conversation-1",
        sender_id: "agent-1",
        role: "assistant",
        kind: "text",
        author: "Daily Chat Agent",
        content: "你好呀，我是上一轮回复。",
        rawContent: { agent_id: "agent-1" },
        createdAt: "2026-06-07T06:20:00.000Z",
        streamState: "done",
        status: "completed",
        state: "active",
      },
    ]);
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        conversation_id: "conversation-1",
        agent_id: "agent-1",
        agent_message_id: "next-agent-message",
        agent_name: "Daily Chat Agent",
      });
    });

    expect(result.current.displayOrder).toHaveLength(1);
    expect(currentStream(result)?.id).toBe("next-agent-message");

    act(() => {
      result.current.streamHandlers.onToken?.("agent-1", "你好呀，这是新回复。", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });

    expect(currentStream(result)?.content).toBe("你");
    flushTypewriter();
    expect(currentStream(result)?.content).toBe("你好呀，这是新回复。");
  });

  it("replaces optimistic user messages when the persisted client message arrives", () => {
    useConversationStore.getState().setActiveId("conversation-1");
    useMessageStore.getState().setMessages([
      {
        id: "local-1",
        conversationId: "conversation-1",
        role: "user",
        kind: "text",
        author: "演示用户",
        content: "你好",
        rawContent: { client_message_id: "client-1" },
        client_message_id: "client-1",
        createdAt: "2026-06-07T06:00:00.000Z",
        streamState: "done",
        state: "active",
      },
    ]);
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageNew?.({
        id: "server-1",
        conversationId: "conversation-1",
        role: "user",
        kind: "text",
        author: "演示用户",
        content: "你好",
        rawContent: { client_message_id: "client-1" },
        client_message_id: "client-1",
        createdAt: "2026-06-07T06:00:01.000Z",
        streamState: "done",
        status: "sent",
        state: "active",
      });
    });

    const messages = useMessageStore.getState().historyMessages;
    expect(messages).toHaveLength(1);
    expect(messages[0]?.id).toBe("server-1");
    expect(messages[0]?.content).toBe("你好");
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

    expect(currentStream(result)?.content).toBe(
      "我",
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
    flushTypewriter();

    expect(useMessageStore.getState().historyMessages).toEqual([persisted]);
    expect(result.current.streamingMessages.size).toBe(0);
    expect(result.current.displayOrder).toEqual([]);
  });

  it("keeps streaming visible for empty persisted placeholders until message update", () => {
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
      result.current.streamHandlers.onToken?.("agent-1", "你好呀", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });

    const placeholder = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "text",
      author: "Daily Chat Agent",
      content: "",
      rawContent: { agent_id: "agent-1" },
      streamState: "streaming",
      status: "streaming",
      state: "active",
    });
    placeholder.id = "persisted-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(placeholder);
    });

    expect(currentStream(result)?.content).toBe("你");

    const completed = {
      ...placeholder,
      content: "你好呀",
      streamState: "done" as const,
      status: "completed",
    };

    act(() => {
      result.current.streamHandlers.onMessageUpdated?.(completed);
    });
    flushTypewriter();

    expect(useMessageStore.getState().historyMessages).toEqual([completed]);
    expect(result.current.streamingMessages.size).toBe(0);
  });

  it("does not treat preview cards as the final streamed text reply", () => {
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
      result.current.streamHandlers.onToken?.("agent-1", "已为你生成 PDF", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });

    const preview = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "preview_card",
      author: "Master Agent",
      content: "预览产物：化学基础实验示例报告",
      rawContent: {
        artifact_id: "artifact-1",
        agent_id: "agent-1",
        title: "化学基础实验示例报告",
        format: "pdf",
      },
      streamState: "done",
      status: "completed",
      state: "active",
    });
    preview.id = "preview-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(preview);
    });

    expect(useMessageStore.getState().historyMessages).toEqual([preview]);
    expect(currentStream(result)?.content).toBe("已");
    flushTypewriter();
    expect(currentStream(result)?.content).toBe(
      "已为你生成 PDF",
    );
  });

  it("shows artifact tool progress until the final agent reply arrives", () => {
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
      result.current.streamHandlers.onToolCallStart?.({
        conversation_id: "conversation-1",
        agent_id: "agent-1",
        agent_name: "Daily Chat Agent",
        tools: ["artifact.create_pdf"],
      });
    });

    expect(currentStream(result)?.content).toBe(
      "正在生成 PDF 产物…",
    );

    const preview = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "preview_card",
      author: "Master Agent",
      content: "预览产物：化学基础实验示例报告",
      rawContent: {
        artifact_id: "artifact-1",
        agent_id: "agent-1",
        title: "化学基础实验示例报告",
        format: "pdf",
      },
      streamState: "done",
      status: "completed",
      state: "active",
    });
    preview.id = "preview-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(preview);
    });

    expect(currentStream(result)?.content).toBe(
      "正在生成 PDF 产物…",
    );

    const finalReply = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "text",
      author: "Daily Chat Agent",
      content: "已生成真实 PDF 产物，可在预览卡片中查看和下载。",
      rawContent: { agent_id: "agent-1" },
      streamState: "done",
      status: "completed",
      state: "active",
    });
    finalReply.id = "agent-final-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(finalReply);
    });

    expect(result.current.streamingMessages.size).toBe(1);
    expect(currentStream(result)?.content).toBe("已");
    flushTypewriter();

    expect(result.current.streamingMessages.size).toBe(0);
    expect(useMessageStore.getState().historyMessages).toEqual([
      preview,
      finalReply,
    ]);
  });

  it("does not persist a transient streaming bubble on global completion", () => {
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
      result.current.streamHandlers.onToken?.("agent-1", "你好呀，很高兴见到你", {
        conversation_id: "conversation-1",
        agent_name: "Daily Chat Agent",
      });
    });

    expect(result.current.streamingMessages.size).toBe(1);

    act(() => {
      result.current.streamHandlers.onDone?.({
        conversation_id: "conversation-1",
        status: "completed",
      });
    });

    expect(result.current.streamingMessages.size).toBe(1);
    flushTypewriter();
    expect(result.current.streamingMessages.size).toBe(1);
    expect(useMessageStore.getState().historyMessages).toEqual([]);

    const persisted = makeMessage({
      conversationId: "conversation-1",
      sender_id: "agent-1",
      sender_type: "agent",
      role: "assistant",
      kind: "text",
      author: "Daily Chat Agent",
      content: "你好呀，很高兴见到你",
      rawContent: { agent_id: "agent-1" },
      streamState: "done",
      status: "completed",
      state: "active",
    });
    persisted.id = "persisted-message-1";

    act(() => {
      result.current.streamHandlers.onMessageNew?.(persisted);
    });

    expect(result.current.streamingMessages.size).toBe(0);
    expect(useMessageStore.getState().historyMessages).toEqual([persisted]);
  });

  it("drains queued characters before committing a stopped stream", () => {
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
    const payload = {
      conversation_id: "conversation-1",
      agent_id: "agent-1",
      agent_message_id: "message-1",
      agent_name: "Daily Chat Agent",
    };

    act(() => {
      result.current.streamHandlers.onMessageStart(payload);
      result.current.streamHandlers.onDelta?.("hello", payload);
    });

    expect(currentStream(result)?.content).toBe("h");

    act(() => {
      result.current.streamHandlers.onMessageEnd(payload);
    });

    expect(currentStream(result)?.content).toBe("h");
    expect(useMessageStore.getState().historyMessages).toEqual([]);

    act(() => {
      vi.advanceTimersByTime(28);
    });

    expect(currentStream(result)?.content).toBe("he");

    flushTypewriter();

    expect(result.current.streamingMessages.size).toBe(0);
    expect(useMessageStore.getState().historyMessages).toHaveLength(1);
    expect(useMessageStore.getState().historyMessages[0]?.content).toBe("hello");
  });
});
