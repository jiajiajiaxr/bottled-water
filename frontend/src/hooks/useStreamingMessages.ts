import { useEffect, useRef, useState } from "react";
import { useMessageStore } from "@/store";
import type { ChatMessage } from "@/types";
import { StreamAssistantHandlers } from "@/types/messages";
import { makeMessage, stripInternalAgentOutput } from "@/lib";

export type StreamState = "idle" | "streaming" | "done" | "error";

function streamKey(payload: Record<string, unknown>): string {
  return String(
    payload.agent_id ||
      payload.agent_message_id ||
      payload.message_id ||
      payload.sender_id ||
      "",
  );
}

/**
 * 管理正在流式生成的 assistant 气泡。
 *
 * 这里刻意只处理本地流式状态，不负责历史消息加载和后端持久化。
 * `message.content` 始终保持为可见文本，原始流式文本保存在
 * `rawContent._streamRawText`，用于持续过滤 status_report 等内部片段。
 */
export function useStreamingMessages(conversationId?: string) {
  const { updateMessages, updateMessageVersions } = useMessageStore();
  const [streamingMessages, setStreamingMessages] = useState<
    Map<string, ChatMessage>
  >(new Map());
  const [displayOrder, setDisplayOrder] = useState<string[]>([]);
  const streamingMessagesRef = useRef(streamingMessages);

  useEffect(() => {
    streamingMessagesRef.current = streamingMessages;
  }, [streamingMessages]);

  const bumpMessageVersion = (agentId: string) => {
    const msg = streamingMessagesRef.current.get(agentId);
    if (!msg) return;
    updateMessageVersions((prev) => {
      const next = new Map(prev);
      next.set(msg.id, (prev.get(msg.id) ?? 0) + 1);
      return next;
    });
  };

  const appendToken = (agentId: string, token: string) => {
    setStreamingMessages((prev) => {
      const existing = prev.get(agentId);
      if (!existing) return prev;

      const next = new Map(prev);
      const rawText =
        String(existing.rawContent?._streamRawText || existing.content || "") +
        token;

      next.set(agentId, {
        ...existing,
        content: stripInternalAgentOutput(rawText),
        rawContent: {
          ...(existing.rawContent || {}),
          _streamRawText: rawText,
        },
      });
      return next;
    });

    bumpMessageVersion(agentId);
  };

  const appendThinking = (agentId: string, thinking: string) => {
    setStreamingMessages((prev) => {
      const existing = prev.get(agentId);
      if (!existing) return prev;

      const next = new Map(prev);
      next.set(agentId, {
        ...existing,
        thinking: (existing.thinking || "") + thinking,
      });
      return next;
    });

    bumpMessageVersion(agentId);
  };

  const streamHandlers: StreamAssistantHandlers = {
    onMessageStart: (payload) => {
      const agentId = streamKey(payload);
      const author = String(
        payload.agent_name || payload.sender_name || "Agent",
      );

      if (!agentId) return;

      setStreamingMessages((prev) => {
        if (prev.has(agentId)) return prev;

        const next = new Map(prev);
        const msg = makeMessage({
          conversationId: conversationId || "",
          role: "assistant",
          kind: "text",
          author,
          content: "",
          rawContent: {
            agent_message_id: payload.agent_message_id,
            message_id: payload.message_id,
            agent_id: payload.agent_id,
            _streamRawText: "",
          },
          streamState: "streaming",
          state: "active",
        });

        msg.id = String(payload.agent_message_id || payload.message_id || msg.id);
        next.set(agentId, msg);
        return next;
      });

      setDisplayOrder((prev) =>
        prev.includes(agentId) ? prev : [...prev, agentId],
      );
    },

    onMessageEnd: (payload) => {
      const agentId = streamKey(payload);
      if (!agentId) return;

      const msg = streamingMessagesRef.current.get(agentId);
      if (!msg) return;

      setStreamingMessages((prev) => {
        if (!prev.has(agentId)) return prev;
        const next = new Map(prev);
        next.delete(agentId);
        return next;
      });
      setDisplayOrder((prev) => prev.filter((id) => id !== agentId));

      updateMessages((prev) => {
        const existingIds = new Set(prev.map((item) => item.id));
        if (existingIds.has(msg.id)) return prev;
        return [
          ...prev,
          {
            ...msg,
            content: stripInternalAgentOutput(msg.content),
            streamState: "done" as const,
          },
        ];
      });

      updateMessageVersions(() => new Map());
    },

    onToken: (agentId, token) => appendToken(agentId, token),

    onDelta: (delta, payload) => {
      const agentId = streamKey(payload);
      if (agentId && delta) appendToken(agentId, delta);
    },

    onReasoningDelta: (delta, payload) => {
      const agentId = streamKey(payload);
      if (agentId && delta) appendThinking(agentId, delta);
    },

    onThinking: (agentId, thinking) => appendThinking(agentId, thinking),

    onDone: () => {},
    onMessageNew: () => {},
    onToolCallStart: () => {},
    onToolCallDone: () => {},
    onControl: () => {},
  };

  return {
    streamingMessages,
    displayOrder,
    streamHandlers,
  };
}
