import { useEffect, useMemo, useRef, useState } from "react";
import { makeMessage, stripInternalAgentOutput } from "../lib";
import { useMessageStore } from "../store";
import { useConversationStore } from "@/store";
import type { ChatMessage } from "../types";
import { StreamAssistantHandlers } from "../types/messages";

export type StreamState = "idle" | "streaming" | "done" | "error";

function artifactIdOf(message: ChatMessage): string {
  const raw = message.rawContent;
  if (!raw || typeof raw !== "object") return "";
  const value = raw.artifact_id || raw.artifactId;
  return typeof value === "string" ? value : "";
}

function samePersistedMessage(left: ChatMessage, right: ChatMessage): boolean {
  if (left.id === right.id) return true;
  if (left.kind !== "preview_card" || right.kind !== "preview_card") return false;
  const leftArtifactId = artifactIdOf(left);
  const rightArtifactId = artifactIdOf(right);
  return Boolean(leftArtifactId && leftArtifactId === rightArtifactId);
}

function streamKey(payload: Record<string, unknown>): string {
  return String(
    payload.agent_id ||
      payload.agent_message_id ||
      payload.message_id ||
      payload.sender_id ||
      "",
  );
}

function conversationOf(
  fallbackConversationId: string | undefined,
  payload?: Record<string, unknown>,
): string {
  return String(
    payload?.conversation_id ||
      payload?.conversationId ||
      fallbackConversationId ||
      "",
  );
}

function scopedStreamKey(
  fallbackConversationId: string | undefined,
  payload: Record<string, unknown>,
): string {
  const agentId = streamKey(payload);
  const targetConversationId = conversationOf(fallbackConversationId, payload);
  return agentId && targetConversationId ? `${targetConversationId}::${agentId}` : "";
}

function agentKeyFromScopedKey(key: string): string {
  return key.includes("::") ? key.split("::").slice(1).join("::") : key;
}

function isActiveConversation(conversationId: string) {
  return useConversationStore.getState().activeId === conversationId;
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

  const activeStreamingMessages = useMemo(() => {
    const next = new Map<string, ChatMessage>();
    for (const [key, message] of streamingMessages) {
      if (message.conversationId === conversationId) {
        next.set(agentKeyFromScopedKey(key), message);
      }
    }
    return next;
  }, [conversationId, streamingMessages]);

  const activeDisplayOrder = useMemo(
    () =>
      displayOrder
        .filter((key) => streamingMessages.get(key)?.conversationId === conversationId)
        .map(agentKeyFromScopedKey),
    [conversationId, displayOrder, streamingMessages],
  );

  const bumpMessageVersion = (scopedKey: string) => {
    const msg = streamingMessagesRef.current.get(scopedKey);
    if (!msg) return;
    updateMessageVersions((prev) => {
      const next = new Map(prev);
      next.set(msg.id, (prev.get(msg.id) ?? 0) + 1);
      return next;
    });
  };

  const ensureMessage = (
    prev: Map<string, ChatMessage>,
    scopedKeyValue: string,
    payload: Record<string, unknown>,
  ): ChatMessage | undefined => {
    const existing = prev.get(scopedKeyValue);
    if (existing) return existing;

    const targetConversationId = conversationOf(conversationId, payload);
    const agentId = streamKey(payload) || agentKeyFromScopedKey(scopedKeyValue);
    if (!targetConversationId || !agentId) return undefined;

    const author = String(
      payload.agent_name ||
        payload.sender_name ||
        payload.name ||
        "Agent",
    );
    const msg = makeMessage({
      conversationId: targetConversationId,
      role: "assistant",
      kind: "text",
      author,
      content: "",
      rawContent: {
        agent_message_id: payload.agent_message_id,
        message_id: payload.message_id,
        agent_id: payload.agent_id || agentId,
        _streamRawText: "",
      },
      streamState: "streaming",
      state: "active",
      status: "streaming",
    });

    msg.id = String(payload.agent_message_id || payload.message_id || msg.id);
    return msg;
  };

  const appendToken = (payload: Record<string, unknown>, token: string) => {
    const key = scopedStreamKey(conversationId, payload);
    if (!key) return;
    setStreamingMessages((prev) => {
      const existing = ensureMessage(prev, key, payload);
      if (!existing) return prev;

      const next = new Map(prev);
      const rawText =
        String(existing.rawContent?._streamRawText || existing.content || "") +
        token;

      next.set(key, {
        ...existing,
        content: stripInternalAgentOutput(rawText),
        rawContent: {
          ...(existing.rawContent || {}),
          _streamRawText: rawText,
        },
      });
      return next;
    });

    setDisplayOrder((prev) => (prev.includes(key) ? prev : [...prev, key]));
    bumpMessageVersion(key);
  };

  const appendThinking = (payload: Record<string, unknown>, thinking: string) => {
    const key = scopedStreamKey(conversationId, payload);
    if (!key) return;
    setStreamingMessages((prev) => {
      const existing = ensureMessage(prev, key, payload);
      if (!existing) return prev;

      const next = new Map(prev);
      const rawThinking =
        String(existing.rawContent?._streamRawThinking || existing.thinking || "") +
        thinking;
      next.set(key, {
        ...existing,
        thinking: stripInternalAgentOutput(rawThinking),
        rawContent: {
          ...(existing.rawContent || {}),
          _streamRawThinking: rawThinking,
        },
      });
      return next;
    });

    setDisplayOrder((prev) => (prev.includes(key) ? prev : [...prev, key]));
    bumpMessageVersion(key);
  };

  const finalizePendingStreams = (targetConversationId = conversationId) => {
    if (!targetConversationId) return;
    const pending = Array.from(streamingMessagesRef.current.entries()).filter(
      ([, message]) => message.conversationId === targetConversationId,
    );
    if (!pending.length) return;

    setStreamingMessages((prev) => {
      const next = new Map(prev);
      pending.forEach(([key]) => next.delete(key));
      return next;
    });
    setDisplayOrder((prev) =>
      prev.filter((key) => streamingMessagesRef.current.get(key)?.conversationId !== targetConversationId),
    );

    if (!isActiveConversation(targetConversationId)) {
      return;
    }

    updateMessages((prev) => {
      const existingIds = new Set(prev.map((item) => item.id));
      const completed = pending
        .map(([, msg]) => ({
          ...msg,
          content: stripInternalAgentOutput(
            String(msg.rawContent?._streamRawText || msg.content || ""),
          ),
          streamState: "done" as const,
          status: msg.status === "failed" ? "failed" : "completed",
        }))
        .filter((msg) => msg.content.trim() && !existingIds.has(msg.id));

      return completed.length ? [...prev, ...completed] : prev;
    });

    updateMessageVersions(() => new Map());
  };

  const clearPendingStreams = (targetConversationId = conversationId) => {
    if (!targetConversationId) return;
    setStreamingMessages((prev) => {
      const next = new Map(prev);
      for (const [key, message] of prev) {
        if (message.conversationId === targetConversationId) {
          next.delete(key);
        }
      }
      return next;
    });
    setDisplayOrder((prev) =>
      prev.filter((key) => streamingMessagesRef.current.get(key)?.conversationId !== targetConversationId),
    );
    updateMessageVersions(() => new Map());
  };

  const streamHandlers: StreamAssistantHandlers = {
    onMessageStart: (payload) => {
      const agentId = streamKey(payload);
      const key = scopedStreamKey(conversationId, payload);
      const author = String(
        payload.agent_name || payload.sender_name || "Agent",
      );

      if (!agentId || !key) return;

      setStreamingMessages((prev) => {
        if (prev.has(key)) return prev;

        const next = new Map(prev);
        const msg = makeMessage({
          conversationId: conversationOf(conversationId, payload),
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
        next.set(key, msg);
        return next;
      });

      setDisplayOrder((prev) =>
        prev.includes(key) ? prev : [...prev, key],
      );
    },

    onMessageEnd: (payload) => {
      const key = scopedStreamKey(conversationId, payload);
      if (!key) return;

      const msg = streamingMessagesRef.current.get(key);
      if (!msg) return;

      setStreamingMessages((prev) => {
        if (!prev.has(key)) return prev;
        const next = new Map(prev);
        next.delete(key);
        return next;
      });
      setDisplayOrder((prev) => prev.filter((id) => id !== key));

      if (!isActiveConversation(msg.conversationId)) return;

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

    onToken: (agentId, token, payload) =>
      appendToken({ ...(payload || {}), agent_id: agentId }, token),

    onDelta: (delta, payload) => {
      if (streamKey(payload) && delta) appendToken(payload, delta);
    },

    onReasoningDelta: (delta, payload) => {
      if (streamKey(payload) && delta) appendThinking(payload, delta);
    },

    onThinking: (agentId, thinking) => appendThinking({ agent_id: agentId }, thinking),

    onDone: (payload) => {
      const targetConversationId = conversationOf(conversationId, payload);
      finalizePendingStreams(targetConversationId);
    },
    onMessageNew: (message) => {
      const senderId = String(message.sender_id || "");
      if (senderId) {
        setStreamingMessages((prev) => {
          const next = new Map(prev);
          for (const [key, item] of prev) {
            if (
              item.conversationId === message.conversationId &&
              String(item.rawContent?.agent_id || "") === senderId
            ) {
              next.delete(key);
            }
          }
          return next;
        });
        setDisplayOrder((prev) =>
          prev.filter((key) => {
            const item = streamingMessagesRef.current.get(key);
            return !(
              item?.conversationId === message.conversationId &&
              String(item?.rawContent?.agent_id || "") === senderId
            );
          }),
        );
      }
      if (!isActiveConversation(message.conversationId)) return;
      updateMessages((prev) => {
        const duplicateIndex = prev.findIndex((item) =>
          samePersistedMessage(item, message),
        );
        if (duplicateIndex >= 0) {
          const next = [...prev];
          next[duplicateIndex] = message;
          return next;
        }
        return [...prev, message];
      });
    },
    onToolCallStart: () => {},
    onToolCallDone: () => {},
    onControl: () => {},
  };

  return {
    streamingMessages: activeStreamingMessages,
    displayOrder: activeDisplayOrder,
    streamHandlers,
    clearPendingStreams,
  };
}
