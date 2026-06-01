import { useRef, useState } from "react";
import { useMessageStore } from "@/store";
import type { ChatMessage } from "@/types";
import { StreamAssistantHandlers } from "@/types/messages";
import { makeMessage } from "@/lib";

export type StreamState = "idle" | "streaming" | "done" | "error";

/**
 * 管理流式消息（streamingMessages）及其渲染版本号。
 *
 * 职责边界：
 * - 只管理"正在传输中"的消息状态，不涉历史消息归档逻辑。
 * - 所有方法均为纯状态操作，不调用 API。
 * - 版本号与 Store 中的 messageVersions 保持同步，用于 MessageBubble memo 优化。
 */
export function useStreamingMessages(conversationId?: string) {
  const { updateMessages, updateMessageVersions } = useMessageStore();

  /** 正在流式传输中的消息池 */
  const [streamingMessages, setStreamingMessages] = useState<
    Map<string, ChatMessage>
  >(new Map());
  const [streamState, setStreamState] = useState<StreamState>("idle");
  const [displayOrder, setDisplayOrder] = useState<string[]>([]);

  /**
   * 用 ref 穿透闭包，确保异步事件回调中读取到最新的 streamingMessages。
   * 否则 React 闭包陷阱会导致 onMessageEnd 读到旧值，无法正确归档。
   */
  const streamingMessagesRef = useRef(streamingMessages);
  streamingMessagesRef.current = streamingMessages;

  const streamHandlers: StreamAssistantHandlers = {
    onMessageStart: (payload) => {
      const agentId = String(payload.agent_id || "");
      const author = String(payload.agent_name || "Agent");

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
          streamState: "streaming",
          state: "active",
        });

        // 使用唯一 ID，避免同一 Agent 多次回复时 ID 冲突导致无法归档
        msg.id = `${agentId}-${Date.now()}`;
        next.set(agentId, msg);

        return next;
      });

      setDisplayOrder((prev) =>
        prev.includes(agentId) ? prev : [...prev, agentId],
      );
    },

    onMessageEnd: (payload) => {
      const agentId = String(payload.agent_id || "");

      if (!agentId) return;

      // 使用 ref 读取最新值，避免闭包陷阱导致 msg 为 undefined
      const msg = streamingMessagesRef.current.get(agentId);

      if (!msg) return;

      setStreamingMessages((prev) => {
        if (!prev.has(agentId)) return prev;
        const next = new Map(prev);
        next.delete(agentId);
        return next;
      });

      setDisplayOrder((prev) => prev.filter((id) => id !== agentId));

      // 提交到历史消息
      updateMessages((prev) => {
        const existingIds = new Set(prev.map((item) => item.id));
        if (existingIds.has(msg.id)) return prev;
        return [...prev, { ...msg, streamState: "done" as const }];
      });

      updateMessageVersions((prev) => {
        return new Map();
      });
    },

    onToken: (agentId, token) => {
      setStreamingMessages((prev) => {
        const existing = prev.get(agentId);

        if (!existing) return prev;

        const next = new Map(prev);

        next.set(agentId, {
          ...existing,
          content: (existing.content || "") + token,
        });

        return next;
      });

      // 使用消息实际 id 作为版本号键，与 MessageBubble 读取的 key 保持一致
      const msg = streamingMessagesRef.current.get(agentId);
      if (msg) {
        updateMessageVersions((prev) => {
          const next = new Map(prev);
          next.set(msg.id, (prev.get(msg.id) ?? 0) + 1);
          return next;
        });
      }
    },

    onThinking: (agentId, thinking) => {
      // setStreamingMessages((prev) => {
      //   const existing = prev.get(agentId);
      //   if (!existing) return prev;
      //   const next = new Map(prev);
      //   next.set(agentId, {
      //     ...existing,
      //     thinking: (existing.thinking || "") + thinking,
      //   });
      //   return next;
      // });
    },

    onDone: () => {
      setStreamState("done");
    },

    // 以下暂时空实现
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
