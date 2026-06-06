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

function persistedMessageId(message: ChatMessage): string {
  const raw = message.rawContent;
  return String(
    raw?.agent_message_id ||
      raw?.message_id ||
      message.id ||
      "",
  );
}

function sameMessageId(left: ChatMessage, right: ChatMessage): boolean {
  const leftId = persistedMessageId(left);
  const rightId = persistedMessageId(right);
  return Boolean(leftId && rightId && leftId === rightId);
}

function samePersistedMessage(left: ChatMessage, right: ChatMessage): boolean {
  if (sameMessageId(left, right)) return true;
  if (left.kind !== "preview_card" || right.kind !== "preview_card") return false;
  const leftArtifactId = artifactIdOf(left);
  const rightArtifactId = artifactIdOf(right);
  return Boolean(leftArtifactId && leftArtifactId === rightArtifactId);
}

function streamKey(payload: Record<string, unknown>): string {
  return String(
    payload.agent_message_id ||
      payload.message_id ||
      payload.agent_id ||
      payload.sender_id ||
      "",
  );
}

function agentIdentity(payload: Record<string, unknown>): string {
  return String(payload.agent_id || payload.sender_id || "");
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

function agentDisplayName(
  conversationId: string,
  agentId: string,
  payload: Record<string, unknown>,
): string {
  const explicit = String(payload.agent_name || payload.sender_name || payload.name || "");
  if (explicit) return explicit;
  const conversation = useConversationStore
    .getState()
    .conversations.find((item) => item.id === conversationId);
  const participant = conversation?.participants.find(
    (item) => item.agent_id === agentId,
  );
  return participant?.agent_name || participant?.nickname || "Agent";
}

function mergeStreamText(current: string, incoming: string): string {
  if (!incoming) return current;
  if (!current) return incoming;
  if (incoming === current || current.endsWith(incoming)) return current;
  if (incoming.startsWith(current)) return incoming;
  return `${current}${incoming}`;
}

function incrementalStreamText(current: string, incoming: string): string {
  const merged = mergeStreamText(current, incoming);
  return merged.startsWith(current) ? merged.slice(current.length) : incoming;
}

function sameTextMessage(left: ChatMessage, right: ChatMessage): boolean {
  if (left.kind !== "text" || right.kind !== "text") return false;
  if (left.conversationId !== right.conversationId) return false;
  if (left.role !== right.role) return false;
  const sameSender =
    Boolean(left.sender_id && left.sender_id === right.sender_id) ||
    Boolean(left.rawContent?.agent_id && left.rawContent.agent_id === right.sender_id) ||
    left.author === right.author;
  return sameSender && left.content.trim() === right.content.trim();
}

function shouldDropStreamForPersisted(
  streamMessage: ChatMessage,
  persistedMessage: ChatMessage,
): boolean {
  if (streamMessage.conversationId !== persistedMessage.conversationId) {
    return false;
  }

  const persistedSenderId = String(persistedMessage.sender_id || "");
  const streamAgentId = String(
    streamMessage.rawContent?.agent_id || streamMessage.sender_id || "",
  );
  const streamMessageId = String(
    streamMessage.rawContent?.agent_message_id ||
      streamMessage.rawContent?.message_id ||
      streamMessage.id ||
      "",
  );
  const persistedMessageId = String(
    persistedMessage.rawContent?.agent_message_id ||
      persistedMessage.rawContent?.message_id ||
      persistedMessage.id ||
      "",
  );
  const terminalPersisted = ["completed", "done", "failed", "cancelled"].includes(
    String(persistedMessage.status || persistedMessage.streamState || ""),
  );

  if (streamMessageId && persistedMessageId && streamMessageId === persistedMessageId) {
    return terminalPersisted || Boolean(persistedMessage.content.trim());
  }
  if (samePersistedMessage(streamMessage, persistedMessage)) {
    return true;
  }
  if (sameTextMessage(streamMessage, persistedMessage)) {
    return true;
  }
  if (
    terminalPersisted &&
    persistedMessage.kind === "text" &&
    persistedMessage.role === "assistant" &&
    persistedSenderId &&
    streamAgentId === persistedSenderId
  ) {
    const streamText = String(
      streamMessage.rawContent?._streamRawText || streamMessage.content || "",
    ).trim();
    const streamThinking = String(
      streamMessage.rawContent?._streamRawThinking || streamMessage.thinking || "",
    ).trim();
    const persistedText = persistedMessage.content.trim();
    if (!streamText || !persistedText || persistedText.includes(streamText) || streamText.includes(persistedText)) {
      return true;
    }
    if (streamThinking && !streamText) {
      return true;
    }
  }
  return Boolean(
    terminalPersisted &&
      persistedMessage.content.trim() &&
      persistedMessage.kind === "text" &&
      persistedMessage.role === "assistant" &&
      persistedSenderId &&
      streamAgentId === persistedSenderId,
  );
}

function isRepresentedByHistory(
  message: ChatMessage,
  historyMessages: ChatMessage[],
): boolean {
  return historyMessages.some((item) => shouldDropStreamForPersisted(message, item));
}

function toolNamesFromPayload(payload: Record<string, unknown>): string[] {
  const names = new Set<string>();
  const addName = (value: unknown) => {
    if (typeof value === "string" && value.trim()) {
      names.add(value.trim());
    }
  };

  addName(payload.tool);
  addName(payload.tool_name);

  const tools = payload.tools;
  if (Array.isArray(tools)) {
    tools.forEach((item) => {
      if (typeof item === "string") {
        addName(item);
        return;
      }
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        addName(record.name);
        addName(record.tool);
        addName(record.tool_name);
        const fn = record.function as Record<string, unknown> | undefined;
        addName(fn?.name);
      }
    });
  }

  return Array.from(names);
}

function artifactProgressText(payload: Record<string, unknown>): string | undefined {
  const labels: Record<string, string> = {
    "artifact.create_pdf": "PDF",
    "artifact.create_docx": "Word",
    "artifact.create_pptx": "PPT",
    "artifact.create_xlsx": "Excel",
    "artifact.create_html": "HTML",
  };
  const toolName = toolNamesFromPayload(payload).find((name) => labels[name]);
  if (!toolName) return undefined;
  return `正在生成 ${labels[toolName]} 产物…`;
}

/**
 * 管理正在流式生成的 assistant 气泡。
 *
 * 这里刻意只处理本地流式状态，不负责历史消息加载和后端持久化。
 * `message.content` 始终保持为可见文本，原始流式文本保存在
 * `rawContent._streamRawText`，用于持续过滤 status_report 等内部片段。
 */
export function useStreamingMessages(conversationId?: string) {
  const { historyMessages, updateMessages, updateMessageVersions } =
    useMessageStore();
  const [streamingMessages, setStreamingMessages] = useState<
    Map<string, ChatMessage>
  >(new Map());
  const [displayOrder, setDisplayOrder] = useState<string[]>([]);
  const streamingMessagesRef = useRef(streamingMessages);
  const hiddenStreamKeysRef = useRef<Set<string>>(new Set());
  const tokenQueuesRef = useRef<Map<string, string[]>>(new Map());
  const tokenTimersRef = useRef<Map<string, number>>(new Map());
  const pendingMessageEndPayloadsRef = useRef<Map<string, Record<string, unknown>>>(
    new Map(),
  );

  useEffect(() => {
    streamingMessagesRef.current = streamingMessages;
  }, [streamingMessages]);

  useEffect(
    () => () => {
      for (const timer of tokenTimersRef.current.values()) {
        window.clearTimeout(timer);
      }
      tokenTimersRef.current.clear();
      tokenQueuesRef.current.clear();
      pendingMessageEndPayloadsRef.current.clear();
    },
    [],
  );

  const activeStreamingMessages = useMemo(() => {
    const next = new Map<string, ChatMessage>();
    for (const [key, message] of streamingMessages) {
      if (message.conversationId === conversationId) {
        if (
          hiddenStreamKeysRef.current.has(key) ||
          isRepresentedByHistory(message, historyMessages)
        ) {
          continue;
        }
        const visibleKey = agentKeyFromScopedKey(key);
        next.set(visibleKey, message);

        const agentId = String(message.rawContent?.agent_id || "");
        if (agentId && !next.has(agentId)) {
          next.set(agentId, message);
        }
      }
    }
    return next;
  }, [conversationId, historyMessages, streamingMessages]);

  const activeDisplayOrder = useMemo(
    () => {
      const keys: string[] = [];
      const seen = new Set<string>();
      for (const key of displayOrder) {
        const message = streamingMessages.get(key);
        if (!message || message.conversationId !== conversationId) continue;
        if (
          hiddenStreamKeysRef.current.has(key) ||
          isRepresentedByHistory(message, historyMessages)
        ) {
          continue;
        }
        const visibleKey = agentKeyFromScopedKey(key);
        if (seen.has(visibleKey)) continue;
        seen.add(visibleKey);
        keys.push(visibleKey);
      }
      return keys;
    },
    [conversationId, displayOrder, historyMessages, streamingMessages],
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
    const agentId = agentIdentity(payload) || agentKeyFromScopedKey(scopedKeyValue);
    if (!targetConversationId || !agentId) return undefined;
    const conversationStore = useConversationStore.getState();
    const streamThinkingEnabled =
      conversationStore.thinkingEnabled.has(targetConversationId) &&
      conversationStore.getThinkingEnabled(targetConversationId);

    const author = agentDisplayName(targetConversationId, agentId, payload);
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
        _streamThinkingEnabled: streamThinkingEnabled,
      },
      streamState: "streaming",
      state: "active",
      status: "streaming",
    });

    msg.id = String(payload.agent_message_id || payload.message_id || msg.id);
    return msg;
  };

  const clearQueuedStream = (key: string) => {
    const timer = tokenTimersRef.current.get(key);
    if (timer) {
      window.clearTimeout(timer);
      tokenTimersRef.current.delete(key);
    }
    tokenQueuesRef.current.delete(key);
  };

  const existingKeyForPayload = (payload: Record<string, unknown>): string => {
    const key = scopedStreamKey(conversationId, payload);
    if (key && streamingMessagesRef.current.has(key)) return key;
    const targetConversationId = conversationOf(conversationId, payload);
    const messageId = String(payload.agent_message_id || payload.message_id || "");
    if (!targetConversationId || !messageId) return key;
    for (const [itemKey, message] of streamingMessagesRef.current) {
      if (message.conversationId !== targetConversationId) continue;
      const rawId = String(
        message.rawContent?.agent_message_id ||
          message.rawContent?.message_id ||
          message.id ||
          "",
      );
      if (rawId === messageId) return itemKey;
    }
    return key;
  };

  const appendTokenNow = (payload: Record<string, unknown>, token: string) => {
    const key = scopedStreamKey(conversationId, payload);
    if (!key) return;
    if (!streamingMessagesRef.current.has(key)) {
      hiddenStreamKeysRef.current.delete(key);
    }
    const existing = ensureMessage(streamingMessagesRef.current, key, payload);
    if (!existing) return;

    const next = new Map(streamingMessagesRef.current);
    const rawText = `${String(
      existing.rawContent?._streamRawText || existing.content || "",
    )}${token}`;
    const nextMessage = {
      ...existing,
      content: stripInternalAgentOutput(rawText),
      rawContent: {
        ...(existing.rawContent || {}),
        _streamRawText: rawText,
      },
    };

    next.set(key, nextMessage);
    streamingMessagesRef.current = next;
    setStreamingMessages(next);

    setDisplayOrder((prev) => (prev.includes(key) ? prev : [...prev, key]));
    bumpMessageVersion(key);
  };

  const finishStreamMessage = (key: string) => {
    const queue = tokenQueuesRef.current.get(key);
    if (queue?.length || tokenTimersRef.current.has(key)) return;

    const msg = streamingMessagesRef.current.get(key);
    if (!msg) {
      pendingMessageEndPayloadsRef.current.delete(key);
      return;
    }
    const pendingPayload = pendingMessageEndPayloadsRef.current.get(key);
    const suppressHistory = pendingPayload?._suppressHistory === true;

    hiddenStreamKeysRef.current.add(key);
    clearQueuedStream(key);

    setStreamingMessages((prev) => {
      if (!prev.has(key)) return prev;
      const next = new Map(prev);
      next.delete(key);
      streamingMessagesRef.current = next;
      return next;
    });
    setDisplayOrder((prev) => prev.filter((id) => id !== key));
    pendingMessageEndPayloadsRef.current.delete(key);

    if (suppressHistory || !isActiveConversation(msg.conversationId)) return;

    const completedMessage = {
      ...msg,
      content: stripInternalAgentOutput(
        String(msg.rawContent?._streamRawText || msg.content || ""),
      ),
      streamState: "done" as const,
      status: msg.status === "failed" ? "failed" : "completed",
    };

    updateMessages((prev) => {
      const byIdIndex = prev.findIndex((item) => sameMessageId(item, msg));
      if (byIdIndex >= 0) {
        const next = [...prev];
        next[byIdIndex] = {
          ...prev[byIdIndex],
          ...completedMessage,
        };
        return next;
      }
      if (
        prev.some(
          (item) =>
            samePersistedMessage(item, msg) || sameTextMessage(item, msg),
        )
      ) {
        return prev;
      }
      return [...prev, completedMessage];
    });

    updateMessageVersions(() => new Map());
  };

  const scheduleTokenDrain = (
    key: string,
    payload: Record<string, unknown>,
  ) => {
    if (tokenTimersRef.current.has(key)) return;
    const timer = window.setTimeout(() => {
      tokenTimersRef.current.delete(key);
      if (hiddenStreamKeysRef.current.has(key)) {
        clearQueuedStream(key);
        return;
      }

      const queue = tokenQueuesRef.current.get(key);
      if (!queue?.length) {
        tokenQueuesRef.current.delete(key);
        if (pendingMessageEndPayloadsRef.current.has(key)) {
          finishStreamMessage(key);
        }
        return;
      }

      const chunk = queue.shift() || "";
      appendTokenNow(payload, chunk);

      if (queue.length) {
        scheduleTokenDrain(key, payload);
      } else {
        tokenQueuesRef.current.delete(key);
        if (pendingMessageEndPayloadsRef.current.has(key)) {
          finishStreamMessage(key);
        }
      }
    }, 18);
    tokenTimersRef.current.set(key, timer);
  };

  const appendToken = (payload: Record<string, unknown>, token: string) => {
    const key = scopedStreamKey(conversationId, payload);
    if (!key || !token) return;

    const existing = streamingMessagesRef.current.get(key);
    if (existing?.rawContent?._toolProgress) {
      clearQueuedStream(key);
      const resetMessage = {
        ...existing,
        content: "",
        rawContent: {
          ...(existing.rawContent || {}),
          _streamRawText: "",
          _toolProgress: false,
        },
      };
      const nextRef = new Map(streamingMessagesRef.current);
      nextRef.set(key, resetMessage);
      streamingMessagesRef.current = nextRef;
      setStreamingMessages((prev) => {
        if (!prev.has(key)) return prev;
        const next = new Map(prev);
        next.set(key, resetMessage);
        return next;
      });
    }

    const queued = tokenQueuesRef.current.get(key) || [];
    const visibleRaw = String(
      streamingMessagesRef.current.get(key)?.rawContent?._streamRawText ||
        streamingMessagesRef.current.get(key)?.content ||
        "",
    );
    const pendingRaw = `${visibleRaw}${queued.join("")}`;
    const incremental = incrementalStreamText(pendingRaw, token);
    if (!incremental) return;

    const pieces = Array.from(incremental);
    const first = pieces.shift();
    if (first && queued.length === 0) {
      appendTokenNow(payload, first);
    } else if (first) {
      pieces.unshift(first);
    }
    if (!pieces.length) return;

    const queue = tokenQueuesRef.current.get(key) || [];
    queue.push(...pieces);
    tokenQueuesRef.current.set(key, queue);
    scheduleTokenDrain(key, payload);
  };

  const appendToolProgress = (payload: Record<string, unknown>) => {
    const text = artifactProgressText(payload);
    const key = scopedStreamKey(conversationId, payload);
    if (!text || !key) return;

    setStreamingMessages((prev) => {
      const existing = ensureMessage(prev, key, payload);
      if (!existing) return prev;
      const currentRaw = String(
        existing.rawContent?._streamRawText || existing.content || "",
      );
      if (currentRaw.trim() && !existing.rawContent?._toolProgress) {
        return prev;
      }

      clearQueuedStream(key);
      const next = new Map(prev);
      const nextMessage = {
        ...existing,
        content: text,
        rawContent: {
          ...(existing.rawContent || {}),
          _streamRawText: text,
          _toolProgress: true,
        },
      };
      next.set(key, nextMessage);
      streamingMessagesRef.current = next;
      return next;
    });

    setDisplayOrder((prev) => (prev.includes(key) ? prev : [...prev, key]));
    bumpMessageVersion(key);
  };

  const appendThinking = (payload: Record<string, unknown>, thinking: string) => {
    const key = scopedStreamKey(conversationId, payload);
    if (!key) return;
    const targetConversationId = conversationOf(conversationId, payload);
    const conversationStore = useConversationStore.getState();
    if (
      conversationStore.thinkingEnabled.has(targetConversationId) &&
      !conversationStore.getThinkingEnabled(targetConversationId)
    ) {
      return;
    }
    if (!streamingMessagesRef.current.has(key)) {
      hiddenStreamKeysRef.current.delete(key);
    }
    setStreamingMessages((prev) => {
      const existing = ensureMessage(prev, key, payload);
      if (!existing) return prev;

      const next = new Map(prev);
      const rawThinking =
        String(existing.rawContent?._streamRawThinking || existing.thinking || "") +
        thinking;
      const nextMessage = {
        ...existing,
        thinking: stripInternalAgentOutput(rawThinking),
        rawContent: {
          ...(existing.rawContent || {}),
          _streamRawThinking: rawThinking,
          _streamThinkingEnabled: true,
        },
      };
      next.set(key, nextMessage);
      streamingMessagesRef.current = next;
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

    if (isActiveConversation(targetConversationId)) {
      pending.forEach(([key]) => {
        pendingMessageEndPayloadsRef.current.set(key, {
          conversation_id: targetConversationId,
          _suppressHistory: true,
        });
        finishStreamMessage(key);
      });
      return;
    }

    setStreamingMessages((prev) => {
      const next = new Map(prev);
      pending.forEach(([key]) => {
        clearQueuedStream(key);
        next.delete(key);
      });
      streamingMessagesRef.current = next;
      return next;
    });
    setDisplayOrder((prev) =>
      prev.filter((key) => streamingMessagesRef.current.get(key)?.conversationId !== targetConversationId),
    );

    if (!isActiveConversation(targetConversationId)) {
      return;
    }

    // Runtime sessions always persist final assistant messages server-side.
    // Do not convert transient streaming bubbles into history here: global
    // completion can arrive before the typewriter queue has drained, which
    // briefly produced a second partial assistant bubble.
    updateMessageVersions(() => new Map());
  };

  const clearPendingStreams = (targetConversationId = conversationId) => {
    if (!targetConversationId) return;
    setStreamingMessages((prev) => {
      const next = new Map(prev);
      for (const [key, message] of prev) {
        if (message.conversationId === targetConversationId) {
          clearQueuedStream(key);
          next.delete(key);
        }
      }
      streamingMessagesRef.current = next;
      return next;
    });
    setDisplayOrder((prev) =>
      prev.filter((key) => streamingMessagesRef.current.get(key)?.conversationId !== targetConversationId),
    );
    updateMessageVersions(() => new Map());
  };

  const streamHandlers: StreamAssistantHandlers = {
    onMessageStart: (payload) => {
      const agentId = agentIdentity(payload) || streamKey(payload);
      const key = scopedStreamKey(conversationId, payload);
      const targetConversationId = conversationOf(conversationId, payload);
      const author = agentDisplayName(targetConversationId, agentId, payload);

      if (!agentId || !key) return;
      if (!streamingMessagesRef.current.has(key)) {
        hiddenStreamKeysRef.current.delete(key);
      }

      setStreamingMessages((prev) => {
        if (prev.has(key)) {
          const existing = prev.get(key);
          if (!existing) return prev;
          const next = new Map(prev);
          next.set(key, {
            ...existing,
            id: String(payload.agent_message_id || payload.message_id || existing.id),
            author,
          rawContent: {
            ...(existing.rawContent || {}),
            agent_message_id: payload.agent_message_id || existing.rawContent?.agent_message_id,
            message_id: payload.message_id || existing.rawContent?.message_id,
            agent_id: payload.agent_id || existing.rawContent?.agent_id || agentId,
            _streamThinkingEnabled: existing.rawContent?._streamThinkingEnabled,
          },
          });
          streamingMessagesRef.current = next;
          return next;
        }

        const next = new Map(prev);
        const msg = makeMessage({
          conversationId: targetConversationId,
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
        streamingMessagesRef.current = next;
        return next;
      });

      setDisplayOrder((prev) =>
        prev.includes(key) ? prev : [...prev, key],
      );
    },

    onMessageEnd: (payload) => {
      const key = existingKeyForPayload(payload);
      if (!key) return;

      const msg = streamingMessagesRef.current.get(key);
      if (!msg) return;
      pendingMessageEndPayloadsRef.current.set(key, payload);
      finishStreamMessage(key);
    },

    onToken: (agentId, token, payload) =>
      appendToken({ ...(payload || {}), agent_id: agentId }, token),

    onDelta: (delta, payload) => {
      if (streamKey(payload) && delta) appendToken(payload, delta);
    },

    onReasoningDelta: (delta, payload) => {
      if (streamKey(payload) && delta) appendThinking(payload, delta);
    },

    onThinking: (agentId, thinking, payload) =>
      appendThinking({ ...(payload || {}), agent_id: agentId }, thinking),

    onDone: (payload) => {
      const targetConversationId = conversationOf(conversationId, payload);
      finalizePendingStreams(targetConversationId);
    },
    onMessageNew: (message) => {
      const keysToHide: string[] = [];
      for (const [key, item] of streamingMessagesRef.current) {
        if (shouldDropStreamForPersisted(item, message)) {
          keysToHide.push(key);
        }
      }
      keysToHide.forEach((key) => hiddenStreamKeysRef.current.add(key));
      if (keysToHide.length) {
        setStreamingMessages((prev) => {
          const next = new Map(prev);
          keysToHide.forEach((key) => {
            clearQueuedStream(key);
            next.delete(key);
          });
          streamingMessagesRef.current = next;
          return next;
        });
        setDisplayOrder((prev) =>
          prev.filter((key) => !hiddenStreamKeysRef.current.has(key)),
        );
      }
      if (!isActiveConversation(message.conversationId)) return;
      updateMessages((prev) => {
        const byIdIndex = prev.findIndex((item) => sameMessageId(item, message));
        if (byIdIndex >= 0) {
          const next = [...prev];
          next[byIdIndex] = message;
          return next;
        }
        const duplicateIndex = prev.findIndex((item) =>
          samePersistedMessage(item, message) || sameTextMessage(item, message),
        );
        if (duplicateIndex >= 0) {
          const next = [...prev];
          next[duplicateIndex] = message;
          return next;
        }
        return [...prev, message];
      });
    },
    onMessageUpdated: (message) => {
      const keysToHide: string[] = [];
      for (const [key, item] of streamingMessagesRef.current) {
        if (shouldDropStreamForPersisted(item, message)) {
          keysToHide.push(key);
        }
      }
      keysToHide.forEach((key) => hiddenStreamKeysRef.current.add(key));
      if (keysToHide.length) {
        setStreamingMessages((prev) => {
          const next = new Map(prev);
          keysToHide.forEach((key) => {
            clearQueuedStream(key);
            next.delete(key);
          });
          streamingMessagesRef.current = next;
          return next;
        });
        setDisplayOrder((prev) =>
          prev.filter((key) => !hiddenStreamKeysRef.current.has(key)),
        );
      }

      if (!isActiveConversation(message.conversationId)) return;
      updateMessages((prev) => {
        const byIdIndex = prev.findIndex((item) => item.id === message.id);
        if (byIdIndex >= 0) {
          const next = [...prev];
          next[byIdIndex] = message;
          return next;
        }

        const duplicateIndex = prev.findIndex((item) =>
          samePersistedMessage(item, message) || sameTextMessage(item, message),
        );
        if (duplicateIndex >= 0) {
          const next = [...prev];
          next[duplicateIndex] = message;
          return next;
        }
        return [...prev, message];
      });
    },
    onToolCallStart: (payload) => appendToolProgress(payload),
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
