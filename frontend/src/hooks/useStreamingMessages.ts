import { useCallback, useState } from "react";
import { useMessageStore } from "@/store";
import type { ChatMessage } from "@/types";

export type StreamState = "idle" | "streaming" | "done" | "error";

/**
 * 自增指定消息的版本号。
 * 返回新的 Map 实例，保证不可变性。
 */
function bumpVersion(
  versions: Map<string, number>,
  messageId: string,
): Map<string, number> {
  const next = new Map(versions);
  next.set(messageId, (next.get(messageId) ?? 0) + 1);
  return next;
}

/**
 * 管理流式消息（streamingMessages）及其渲染版本号。
 *
 * 职责边界：
 * - 只管理"正在传输中"的消息状态，不涉历史消息归档逻辑。
 * - 所有方法均为纯状态操作，不调用 API。
 * - 版本号与 Store 中的 messageVersions 保持同步，用于 MessageBubble memo 优化。
 */
export function useStreamingMessages() {
  const { updateMessages, updateMessageVersions } = useMessageStore();

  /** 正在流式传输中的消息池 */
  const [streamingMessages, setStreamingMessages] = useState<
    Map<string, ChatMessage>
  >(new Map());

  /** 当前流式传输的整体状态 */
  const [streamState, setStreamState] = useState<StreamState>("idle");

  // === 基础操作：只修改 streamingMessages，不涉及历史消息 ===

  /** 将一条新消息加入流式消息池，并标记为 streaming */
  const startStreamingMessage = useCallback(
    (message: ChatMessage) => {
      setStreamingMessages((prev) => {
        const next = new Map(prev);
        next.set(message.id, { ...message, streamState: "streaming" as const });
        return next;
      });
      updateMessageVersions((prev) => bumpVersion(prev, message.id));
    },
    [updateMessageVersions],
  );

  /** 更新指定流式消息的内容字段（支持增量追加）。 */
  const updateStreamingContent = useCallback(
    (messageId: string, updater: (prev: string) => string) => {
      const msg = streamingMessages.get(messageId);
      if (!msg) return;
      const newContent = updater(msg.content || "");

      console.log(msg);

      if (msg.content === newContent) return;
      setStreamingMessages((prev) => {
        const existing = prev.get(messageId);
        if (!existing || existing.content === newContent) return prev;
        const next = new Map(prev);
        next.set(messageId, { ...existing, content: newContent });
        return next;
      });
      updateMessageVersions((prev) => bumpVersion(prev, messageId));
    },
    [streamingMessages, updateMessageVersions],
  );

  /** 更新指定流式消息的 thinking 字段（支持增量追加）。 */
  const updateStreamingThinking = useCallback(
    (messageId: string, updater: string | ((prev: string) => string)) => {
      const msg = streamingMessages.get(messageId);
      if (!msg) return;
      const newThinking =
        typeof updater === "function" ? updater(msg.thinking || "") : updater;
      if (msg.thinking === newThinking) return;
      setStreamingMessages((prev) => {
        const existing = prev.get(messageId);
        if (!existing || existing.thinking === newThinking) return prev;
        const next = new Map(prev);
        next.set(messageId, { ...existing, thinking: newThinking });
        return next;
      });
      updateMessageVersions((prev) => bumpVersion(prev, messageId));
    },
    [streamingMessages, updateMessageVersions],
  );

  /** 对指定流式消息应用 patch（任意字段） */
  const updateStreamingState = useCallback(
    (messageId: string, patch: Partial<ChatMessage>) => {
      const msg = streamingMessages.get(messageId);
      if (!msg) return;
      setStreamingMessages((prev) => {
        const existing = prev.get(messageId);
        if (!existing) return prev;
        const next = new Map(prev);
        next.set(messageId, { ...existing, ...patch });
        return next;
      });
      updateMessageVersions((prev) => bumpVersion(prev, messageId));
    },
    [streamingMessages, updateMessageVersions],
  );

  /** 从流式消息池中移除指定消息 */
  const removeStreamingMessage = useCallback((messageId: string) => {
    setStreamingMessages((prev) => {
      if (!prev.has(messageId)) return prev;
      const next = new Map(prev);
      next.delete(messageId);
      return next;
    });
  }, []);

  // === 组合操作：流式 -> 历史（归档）===

  /**
   * 将单条流式消息归档到历史消息，并从流式池中移除。
   * 这是流式生命周期结束的标准操作。
   *
   * @param patch - 归档前应用的额外字段（如错误状态、清理后的内容）
   */
  const finishStreamingMessage = useCallback(
    (messageId: string, patch?: Partial<ChatMessage>) => {
      const msg = streamingMessages.get(messageId);
      if (!msg) return;
      setStreamingMessages((prev) => {
        const next = new Map(prev);
        next.delete(messageId);
        return next;
      });
      updateMessages((prev) => {
        const existingIds = new Set(prev.map((item) => item.id));
        const archived = { ...msg, ...patch, streamState: "done" as const };
        if (existingIds.has(archived.id)) return prev;
        return [...prev, archived];
      });
      updateMessageVersions((prev) => bumpVersion(prev, messageId));
    },
    [streamingMessages, updateMessages, updateMessageVersions],
  );

  // === 显示顺序管理 ===

  /** 本轮次中 Agent 消息的显示顺序（按 agent_started 到达顺序） */
  const [displayOrder, setDisplayOrder] = useState<string[]>([]);

  const addToDisplayOrder = useCallback((agentId: string) => {
    setDisplayOrder((prev) => {
      if (prev.includes(agentId)) return prev;
      return [...prev, agentId];
    });
  }, []);

  const resetDisplayOrder = useCallback(() => {
    setDisplayOrder([]);
  }, []);

  /**
   * 将流式消息池中所有消息批量归档到历史消息，并清空池子。
   * 用于 SSE onDone 时的批量收尾。
   *
   * @param cleanup - 归档前对每条消息应用的清理函数（如内容净化、工具状态重置）
   */
  const finishAllStreamingMessages = useCallback(
    (cleanup?: (msg: ChatMessage) => Partial<ChatMessage>) => {
      if (!streamingMessages.size) return;
      const doneMessages = Array.from(streamingMessages.values()).map(
        (msg) => ({
          ...msg,
          ...(cleanup ? cleanup(msg) : {}),
          streamState: "done" as const,
        }),
      );
      updateMessages((prev) => {
        const existingIds = new Set(prev.map((item) => item.id));
        const newMessages = doneMessages.filter(
          (msg) => !existingIds.has(msg.id),
        );
        return [...prev, ...newMessages];
      });
      updateMessageVersions((prev) => {
        let next = prev;
        for (const msg of doneMessages) {
          next = bumpVersion(next, msg.id);
        }
        return next;
      });
      setStreamingMessages(new Map());
      setDisplayOrder([]);
    },
    [streamingMessages, updateMessages, updateMessageVersions],
  );

  return {
    streamingMessages,
    streamState,
    setStreamState,
    displayOrder,
    addToDisplayOrder,
    resetDisplayOrder,
    startStreamingMessage,
    updateStreamingContent,
    updateStreamingThinking,
    updateStreamingState,
    removeStreamingMessage,
    finishStreamingMessage,
    finishAllStreamingMessages,
    getStreamingMessages: () => streamingMessages,
  };
}
