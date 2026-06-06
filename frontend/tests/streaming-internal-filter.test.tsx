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

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe("可");
    flushTypewriter();

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
    flushTypewriter();

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

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe("v");
    flushTypewriter();

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
    flushTypewriter();

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

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe("你");

    const completed = {
      ...placeholder,
      content: "你好呀",
      streamState: "done" as const,
      status: "completed",
    };

    act(() => {
      result.current.streamHandlers.onMessageUpdated?.(completed);
    });

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
    expect(result.current.streamingMessages.get("agent-1")?.content).toBe("已");
    flushTypewriter();
    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
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

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
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

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
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

    expect(result.current.streamingMessages.size).toBe(0);
    expect(useMessageStore.getState().historyMessages).toEqual([
      preview,
      finalReply,
    ]);
  });
});
