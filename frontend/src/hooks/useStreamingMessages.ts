import { useEffect, useMemo, useRef, useState } from "react";
import { makeMessage, stripInternalAgentOutput } from "../lib";
import { useMessageStore } from "../store";
import { useConversationStore } from "@/store";
import type { ChatMessage } from "../types";
import { StreamAssistantHandlers } from "../types/messages";

const conversationThinkingMode = new Map<string, boolean>();

export function setConversationThinkingMode(
  conversationId: string,
  enabled: boolean,
) {
  conversationThinkingMode.set(conversationId, enabled);
}

export function clearConversationThinkingMode(conversationId: string) {
  conversationThinkingMode.delete(conversationId);
}

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

function clientMessageIdOf(message: ChatMessage): string {
  const raw = message.rawContent;
  return String(
    message.clientMessageId ||
      message.client_message_id ||
      raw?.clientMessageId ||
      raw?.client_message_id ||
      "",
  );
}

function sameMessageId(left: ChatMessage, right: ChatMessage): boolean {
  const leftId = persistedMessageId(left);
  const rightId = persistedMessageId(right);
  return Boolean(leftId && rightId && leftId === rightId);
}

function sameClientMessage(left: ChatMessage, right: ChatMessage): boolean {
  const leftId = clientMessageIdOf(left);
  const rightId = clientMessageIdOf(right);
  return Boolean(leftId && rightId && leftId === rightId);
}

function samePersistedMessage(left: ChatMessage, right: ChatMessage): boolean {
  if (sameMessageId(left, right)) return true;
  if (sameClientMessage(left, right)) return true;
  if (left.kind !== "preview_card" || right.kind !== "preview_card") return false;
  const leftArtifactId = artifactIdOf(left);
  const rightArtifactId = artifactIdOf(right);
  return Boolean(leftArtifactId && leftArtifactId === rightArtifactId);
}

function sameOptimisticUserMessage(left: ChatMessage, right: ChatMessage): boolean {
  if (left.conversationId !== right.conversationId) return false;
  if (left.role !== "user" || right.role !== "user") return false;
  if (left.content.trim() !== right.content.trim()) return false;
  const hasLocalMessage =
    left.id.startsWith("local-") || right.id.startsWith("local-");
  if (!hasLocalMessage) return false;
  const leftTime = Date.parse(left.createdAt);
  const rightTime = Date.parse(right.createdAt);
  if (!Number.isFinite(leftTime) || !Number.isFinite(rightTime)) return true;
  return Math.abs(leftTime - rightTime) <= 5 * 60 * 1000;
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

function payloadAgentAvatarUrl(payload: Record<string, unknown>) {
  const value = payload.agent_avatar_url || payload.sender_avatar_url;
  return typeof value === "string" && value.trim() ? value : undefined;
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

function safePersistedSuffix(current: string, incoming: string): string {
  if (!incoming) return "";
  if (!current) return incoming;
  if (incoming === current || current.endsWith(incoming)) return "";
  return incoming.startsWith(current) ? incoming.slice(current.length) : "";
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
    if (
      streamText &&
      persistedText &&
      (persistedText.includes(streamText) || streamText.includes(persistedText))
    ) {
      return true;
    }
    if (streamText) {
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
      streamAgentId === persistedSenderId &&
      String(streamMessage.rawContent?._streamRawText || streamMessage.content || "").trim(),
  );
}

function mergePersistedWithStreamThinking(
  persistedMessage: ChatMessage,
  streamMessage: ChatMessage | undefined,
): ChatMessage {
  if (!streamMessage) return persistedMessage;
  const persistedThinking = String(persistedMessage.thinking || "").trim();
  if (persistedThinking) return persistedMessage;

  const streamThinking = String(
    streamMessage.thinking ||
      streamMessage.rawContent?._streamRawThinking ||
      "",
  ).trim();
  if (!streamThinking) return persistedMessage;

  return {
    ...persistedMessage,
    thinking: streamThinking,
    rawContent: {
      ...(persistedMessage.rawContent || {}),
      thinking_enabled:
        persistedMessage.rawContent?.thinking_enabled ??
        streamMessage.rawContent?._streamThinkingEnabled ??
        false,
      _streamThinkingEnabled:
        persistedMessage.rawContent?._streamThinkingEnabled ??
        streamMessage.rawContent?._streamThinkingEnabled ??
        true,
      _streamRawThinking:
        persistedMessage.rawContent?._streamRawThinking || streamThinking,
    },
  };
}

function isRepresentedByHistory(
  message: ChatMessage,
  historyMessages: ChatMessage[],
): boolean {
  const boundaryIds = new Set(
    Array.isArray(message.rawContent?._streamHistoryBoundaryIds)
      ? (message.rawContent?._streamHistoryBoundaryIds as unknown[]).map(String)
      : [],
  );
  return historyMessages.some((item) => {
    if (boundaryIds.has(item.id)) return false;
    return shouldDropStreamForPersisted(message, item);
  });
}

function upsertPersistedHistoryMessage(
  messages: ChatMessage[],
  message: ChatMessage,
): ChatMessage[] {
  const existingIndex = messages.findIndex(
    (item) =>
      sameMessageId(item, message) ||
      sameClientMessage(item, message) ||
      samePersistedMessage(item, message) ||
      sameOptimisticUserMessage(item, message),
  );
  if (existingIndex >= 0) {
    const next = [...messages];
    next[existingIndex] = {
      ...messages[existingIndex],
      ...message,
      rawContent: {
        ...(messages[existingIndex].rawContent || {}),
        ...(message.rawContent || {}),
      },
    };
    return next;
  }
  return [...messages, message];
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
  const {
    historyMessages,
    updateMessagesForConversation,
    updateMessageVersions,
  } =
    useMessageStore();
  const [streamingMessages, setStreamingMessages] = useState<
    Map<string, ChatMessage>
  >(new Map());
  const [displayOrder, setDisplayOrder] = useState<string[]>([]);
  const streamingMessagesRef = useRef(streamingMessages);
  const hiddenStreamKeysRef = useRef<Set<string>>(new Set());
  const tokenQueuesRef = useRef<Map<string, string[]>>(new Map());
  const tokenTimersRef = useRef<Map<string, number>>(new Map());
  const thinkingQueuesRef = useRef<Map<string, string[]>>(new Map());
  const thinkingTimersRef = useRef<Map<string, number>>(new Map());
  const pendingMessageEndPayloadsRef = useRef<Map<string, Record<string, unknown>>>(
    new Map(),
  );
  const pendingPersistedMessagesRef = useRef<Map<string, ChatMessage>>(new Map());

  useEffect(() => {
    streamingMessagesRef.current = streamingMessages;
  }, [streamingMessages]);

  useEffect(
    () => () => {
      for (const timer of tokenTimersRef.current.values()) {
        window.clearTimeout(timer);
      }
      for (const timer of thinkingTimersRef.current.values()) {
        window.clearTimeout(timer);
      }
      tokenTimersRef.current.clear();
      tokenQueuesRef.current.clear();
      thinkingTimersRef.current.clear();
      thinkingQueuesRef.current.clear();
      pendingMessageEndPayloadsRef.current.clear();
      pendingPersistedMessagesRef.current.clear();
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
    const streamThinkingEnabled =
      payload.thinking_enabled === true ||
      conversationThinkingMode.get(targetConversationId) === true;

    const author = agentDisplayName(targetConversationId, agentId, payload);
    const agentAvatarUrl = payloadAgentAvatarUrl(payload);
    const historyBoundaryIds = historyMessages
      .filter((message) => message.conversationId === targetConversationId)
      .map((message) => message.id);
    const msg = makeMessage({
      conversationId: targetConversationId,
      role: "assistant",
      kind: "text",
      author,
      content: "",
      sender_avatar_url: agentAvatarUrl,
      rawContent: {
        agent_message_id: payload.agent_message_id,
        message_id: payload.message_id,
        agent_id: payload.agent_id || agentId,
        agent_avatar_url: agentAvatarUrl,
        thinking_enabled: streamThinkingEnabled,
        _streamRawText: "",
        _streamThinkingEnabled: streamThinkingEnabled,
        _streamHistoryBoundaryIds: historyBoundaryIds,
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

  const clearQueuedThinking = (key: string) => {
    const timer = thinkingTimersRef.current.get(key);
    if (timer) {
      window.clearTimeout(timer);
      thinkingTimersRef.current.delete(key);
    }
    thinkingQueuesRef.current.delete(key);
  };

  const hasPendingThinking = (key: string) =>
    Boolean(thinkingTimersRef.current.has(key) || thinkingQueuesRef.current.get(key)?.length);

  const existingKeyForPayload = (payload: Record<string, unknown>): string => {
    const key = scopedStreamKey(conversationId, payload);
    if (key && streamingMessagesRef.current.has(key)) return key;
    const targetConversationId = conversationOf(conversationId, payload);
    const messageId = String(payload.agent_message_id || payload.message_id || "");
    const agentId = String(payload.agent_id || payload.sender_id || "");
    if (!targetConversationId) return key;
    for (const [itemKey, message] of streamingMessagesRef.current) {
      if (message.conversationId !== targetConversationId) continue;
      const rawId = String(
        message.rawContent?.agent_message_id ||
          message.rawContent?.message_id ||
          message.id ||
          "",
      );
      if (messageId && rawId === messageId) return itemKey;
    }
    if (messageId) return key;
    if (!agentId) return key;
    for (const [itemKey, message] of streamingMessagesRef.current) {
      if (message.conversationId !== targetConversationId) continue;
      const rawAgentId = String(
        message.rawContent?.agent_id || message.sender_id || "",
      );
      if (agentId && rawAgentId === agentId) return itemKey;
    }
    return key;
  };

  const appendTokenNow = (payload: Record<string, unknown>, token: string) => {
    const key = existingKeyForPayload(payload) || scopedStreamKey(conversationId, payload);
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
      id: String(payload.agent_message_id || payload.message_id || existing.id),
      sender_avatar_url:
        payloadAgentAvatarUrl(payload) || existing.sender_avatar_url,
      content: stripInternalAgentOutput(rawText),
      rawContent: {
        ...(existing.rawContent || {}),
        agent_message_id:
          payload.agent_message_id || existing.rawContent?.agent_message_id,
        message_id: payload.message_id || existing.rawContent?.message_id,
        agent_id:
          payload.agent_id || payload.sender_id || existing.rawContent?.agent_id,
        agent_avatar_url:
          payloadAgentAvatarUrl(payload) || existing.rawContent?.agent_avatar_url,
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
    const thinkingQueue = thinkingQueuesRef.current.get(key);
    if (
      queue?.length ||
      tokenTimersRef.current.has(key) ||
      thinkingQueue?.length ||
      thinkingTimersRef.current.has(key)
    ) {
      return;
    }

    const msg = streamingMessagesRef.current.get(key);
    if (!msg) {
      pendingMessageEndPayloadsRef.current.delete(key);
      return;
    }
    const pendingPayload = pendingMessageEndPayloadsRef.current.get(key);
    const suppressHistory = pendingPayload?._suppressHistory === true;

    hiddenStreamKeysRef.current.add(key);
    clearQueuedStream(key);
    clearQueuedThinking(key);

    const pendingPersisted = pendingPersistedMessagesRef.current.get(key);
    if (pendingPersisted) {
      pendingPersistedMessagesRef.current.delete(key);
    }

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

    const completedMessage = pendingPersisted ?? {
      ...msg,
      content: stripInternalAgentOutput(
        String(msg.rawContent?._streamRawText || msg.content || ""),
      ),
      streamState: "done" as const,
      status: msg.status === "failed" ? "failed" : "completed",
    };

    updateMessagesForConversation(msg.conversationId, (prev) =>
      upsertPersistedHistoryMessage(prev, completedMessage),
    );

    updateMessageVersions(() => new Map());
  };

  const scheduleTokenDrain = (
    key: string,
    payload: Record<string, unknown>,
  ) => {
    if (tokenTimersRef.current.has(key)) return;
    if (hasPendingThinking(key)) return;
    const timer = window.setTimeout(() => {
      tokenTimersRef.current.delete(key);
      if (hasPendingThinking(key)) {
        scheduleTokenDrain(key, payload);
        return;
      }
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
    }, 28);
    tokenTimersRef.current.set(key, timer);
  };

  const appendThinkingNow = (payload: Record<string, unknown>, chunk: string) => {
    const key = existingKeyForPayload(payload) || scopedStreamKey(conversationId, payload);
    if (!key) return;
    if (!streamingMessagesRef.current.has(key)) {
      hiddenStreamKeysRef.current.delete(key);
    }
    const existing = ensureMessage(streamingMessagesRef.current, key, payload);
    if (!existing) return;

    const next = new Map(streamingMessagesRef.current);
    const rawThinking = `${String(
      existing.rawContent?._streamRawThinking || existing.thinking || "",
    )}${chunk}`;
    const nextMessage = {
      ...existing,
      id: String(payload.agent_message_id || payload.message_id || existing.id),
      sender_avatar_url:
        payloadAgentAvatarUrl(payload) || existing.sender_avatar_url,
      thinking: stripInternalAgentOutput(rawThinking),
      rawContent: {
        ...(existing.rawContent || {}),
        agent_message_id:
          payload.agent_message_id || existing.rawContent?.agent_message_id,
        message_id: payload.message_id || existing.rawContent?.message_id,
        agent_id:
          payload.agent_id || payload.sender_id || existing.rawContent?.agent_id,
        agent_avatar_url:
          payloadAgentAvatarUrl(payload) || existing.rawContent?.agent_avatar_url,
        _streamRawThinking: rawThinking,
        thinking_enabled:
          existing.rawContent?.thinking_enabled ??
          (payload.thinking_enabled === true),
        _streamThinkingEnabled:
          existing.rawContent?._streamThinkingEnabled ??
          existing.rawContent?.thinking_enabled ??
          (payload.thinking_enabled === true),
      },
    };
    next.set(key, nextMessage);
    streamingMessagesRef.current = next;
    setStreamingMessages(next);

    setDisplayOrder((prev) => (prev.includes(key) ? prev : [...prev, key]));
    bumpMessageVersion(key);
  };

  const scheduleThinkingDrain = (
    key: string,
    payload: Record<string, unknown>,
  ) => {
    if (thinkingTimersRef.current.has(key)) return;
    const timer = window.setTimeout(() => {
      thinkingTimersRef.current.delete(key);
      if (hiddenStreamKeysRef.current.has(key)) {
        clearQueuedThinking(key);
        return;
      }

      const queue = thinkingQueuesRef.current.get(key);
      if (!queue?.length) {
        thinkingQueuesRef.current.delete(key);
        if (
          tokenQueuesRef.current.get(key)?.length &&
          !tokenTimersRef.current.has(key)
        ) {
          scheduleTokenDrain(key, payload);
          return;
        }
        if (pendingMessageEndPayloadsRef.current.has(key)) {
          finishStreamMessage(key);
        }
        return;
      }

      const chunk = queue.shift() || "";
      appendThinkingNow(payload, chunk);

      if (queue.length) {
        scheduleThinkingDrain(key, payload);
      } else {
        thinkingQueuesRef.current.delete(key);
        if (
          tokenQueuesRef.current.get(key)?.length &&
          !tokenTimersRef.current.has(key)
        ) {
          scheduleTokenDrain(key, payload);
          return;
        }
        if (pendingMessageEndPayloadsRef.current.has(key)) {
          finishStreamMessage(key);
        }
      }
    }, 24);
    thinkingTimersRef.current.set(key, timer);
  };

  const appendToken = (payload: Record<string, unknown>, token: string) => {
    const key = existingKeyForPayload(payload) || scopedStreamKey(conversationId, payload);
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
    const thinkingPending = hasPendingThinking(key);
    const first = thinkingPending ? undefined : pieces.shift();
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
    const key = existingKeyForPayload(payload) || scopedStreamKey(conversationId, payload);
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
        id: String(payload.agent_message_id || payload.message_id || existing.id),
        content: text,
        rawContent: {
          ...(existing.rawContent || {}),
          agent_message_id:
            payload.agent_message_id || existing.rawContent?.agent_message_id,
          message_id: payload.message_id || existing.rawContent?.message_id,
          agent_id:
            payload.agent_id || payload.sender_id || existing.rawContent?.agent_id,
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

  const replayPersistedMessage = (message: ChatMessage) => {
    if (message.role !== "assistant" || message.kind !== "text") {
      return false;
    }
    const targetConversationId = message.conversationId;
    if (!isActiveConversation(targetConversationId)) {
      return false;
    }
    const streamId = String(
      message.rawContent?.agent_message_id ||
        message.rawContent?.message_id ||
        message.id ||
        "",
    );
    const agentId = String(
      message.rawContent?.agent_id || message.sender_id || "",
    );
    if (!streamId || !agentId || streamingMessagesRef.current.has(`${targetConversationId}::${streamId}`)) {
      return false;
    }

    const thinkingEnabled =
      message.rawContent?.thinking_enabled === true ||
      message.rawContent?._streamThinkingEnabled === true;
    const thinkingText = String(message.thinking || "").trim();
    const visibleText = stripInternalAgentOutput(String(message.content || ""));
    const key = `${targetConversationId}::${streamId}`;
    const payload = {
      conversation_id: targetConversationId,
      agent_message_id: streamId,
      message_id: streamId,
      agent_id: agentId,
      agent_name: message.author,
      thinking_enabled: thinkingEnabled,
    };

    const replayMessage: ChatMessage = {
      ...message,
      id: streamId,
      content: "",
      thinking: "",
      streamState: "streaming",
      status: "streaming",
      rawContent: {
        ...(message.rawContent || {}),
        agent_message_id: streamId,
        message_id: streamId,
        agent_id: agentId,
        thinking_enabled: thinkingEnabled,
        _streamThinkingEnabled: thinkingEnabled,
        _streamRawText: "",
        _streamRawThinking: "",
      },
    };

    setStreamingMessages((prev) => {
      const next = new Map(prev);
      next.set(key, replayMessage);
      streamingMessagesRef.current = next;
      return next;
    });
    setDisplayOrder((prev) => (prev.includes(key) ? prev : [...prev, key]));

    pendingPersistedMessagesRef.current.set(key, message);
    pendingMessageEndPayloadsRef.current.set(key, {
      conversation_id: targetConversationId,
    });

    if (thinkingEnabled && thinkingText) {
      thinkingQueuesRef.current.set(key, Array.from(thinkingText));
      scheduleThinkingDrain(key, payload);
    }
    if (visibleText) {
      tokenQueuesRef.current.set(key, Array.from(visibleText));
      if (!thinkingEnabled || !thinkingText) {
        scheduleTokenDrain(key, payload);
      }
    }
    if ((!thinkingEnabled || !thinkingText) && !visibleText) {
      finishStreamMessage(key);
    }
    return true;
  };

  const appendThinking = (payload: Record<string, unknown>, thinking: string) => {
    const key = existingKeyForPayload(payload);
    if (!key) return;
    if (!streamingMessagesRef.current.has(key)) {
      hiddenStreamKeysRef.current.delete(key);
    }
    const existing = ensureMessage(streamingMessagesRef.current, key, payload);
    if (!existing) return;

    const queued = thinkingQueuesRef.current.get(key) || [];
    const visibleRaw = String(
      streamingMessagesRef.current.get(key)?.rawContent?._streamRawThinking ||
        streamingMessagesRef.current.get(key)?.thinking ||
        "",
    );
    const pendingRaw = `${visibleRaw}${queued.join("")}`;
    const incremental = incrementalStreamText(pendingRaw, thinking);
    if (!incremental) return;

    const pieces = Array.from(incremental);
    const first = pieces.shift();
    if (first && queued.length === 0) {
      appendThinkingNow(payload, first);
    } else if (first) {
      pieces.unshift(first);
    }
    if (!pieces.length) return;

    const queue = thinkingQueuesRef.current.get(key) || [];
    queue.push(...pieces);
    thinkingQueuesRef.current.set(key, queue);
    scheduleThinkingDrain(key, payload);
  };

  const queuePersistedRemainder = (
    key: string,
    streamMessage: ChatMessage,
    persistedMessage: ChatMessage,
  ) => {
    const persistedThinking = String(
      persistedMessage.thinking ||
        persistedMessage.rawContent?._streamRawThinking ||
        "",
    ).trim();
    const persistedText = stripInternalAgentOutput(
      String(persistedMessage.content || ""),
    );
    const agentId = String(
      persistedMessage.rawContent?.agent_id ||
        persistedMessage.sender_id ||
        streamMessage.rawContent?.agent_id ||
        streamMessage.sender_id ||
        "",
    );
    const messageId = String(
      persistedMessage.rawContent?.agent_message_id ||
        persistedMessage.rawContent?.message_id ||
        streamMessage.rawContent?.agent_message_id ||
        streamMessage.rawContent?.message_id ||
        "",
    );
    const thinkingEnabled = Boolean(
      persistedThinking ||
        persistedMessage.rawContent?.thinking_enabled === true ||
        persistedMessage.rawContent?._streamThinkingEnabled === true ||
        streamMessage.rawContent?.thinking_enabled === true ||
        streamMessage.rawContent?._streamThinkingEnabled === true,
    );
    const payload = {
      conversation_id: persistedMessage.conversationId,
      agent_id: agentId,
      agent_name: persistedMessage.author || streamMessage.author,
      thinking_enabled: thinkingEnabled,
      ...(messageId
        ? {
            agent_message_id: messageId,
            message_id: messageId,
          }
        : {}),
    };

    if (thinkingEnabled && persistedThinking) {
      const queuedThinking = thinkingQueuesRef.current.get(key) || [];
      const visibleThinking = String(
        streamingMessagesRef.current.get(key)?.rawContent?._streamRawThinking ||
          streamingMessagesRef.current.get(key)?.thinking ||
          "",
      );
      const thinkingSuffix = safePersistedSuffix(
        `${visibleThinking}${queuedThinking.join("")}`,
        persistedThinking,
      );
      if (thinkingSuffix) appendThinking(payload, thinkingSuffix);
    }
    if (persistedText) {
      const queuedText = tokenQueuesRef.current.get(key) || [];
      const currentStreamMessage = streamingMessagesRef.current.get(key);
      const visibleText = String(
        currentStreamMessage?.rawContent?._toolProgress
          ? ""
          : currentStreamMessage?.rawContent?._streamRawText ||
              currentStreamMessage?.content ||
              "",
      );
      const textSuffix = safePersistedSuffix(
        `${visibleText}${queuedText.join("")}`,
        persistedText,
      );
      if (textSuffix) appendToken(payload, textSuffix);
    }
  };

  const ingestPersistedMessage = (message: ChatMessage) => {
    let mergedMessage = message;
    const keysToHide: string[] = [];
    const keysToDefer: string[] = [];
    for (const [key, item] of streamingMessagesRef.current) {
      if (shouldDropStreamForPersisted(item, message)) {
        mergedMessage = mergePersistedWithStreamThinking(mergedMessage, item);
        if (item.streamState === "streaming") {
          keysToDefer.push(key);
          queuePersistedRemainder(key, item, mergedMessage);
          pendingPersistedMessagesRef.current.set(key, mergedMessage);
          if (!pendingMessageEndPayloadsRef.current.has(key)) {
            pendingMessageEndPayloadsRef.current.set(key, {
              conversation_id: mergedMessage.conversationId,
              _synthetic_from_persisted: true,
            });
          }
        } else {
          keysToHide.push(key);
        }
      }
    }
    keysToHide.forEach((key) => hiddenStreamKeysRef.current.add(key));
    if (keysToHide.length) {
      setStreamingMessages((prev) => {
        const next = new Map(prev);
        keysToHide.forEach((key) => {
          clearQueuedStream(key);
          clearQueuedThinking(key);
          pendingPersistedMessagesRef.current.delete(key);
          next.delete(key);
        });
        streamingMessagesRef.current = next;
        return next;
      });
      setDisplayOrder((prev) =>
        prev.filter((key) => !hiddenStreamKeysRef.current.has(key)),
      );
    }
    if (keysToDefer.length) {
      keysToDefer.forEach((key) => finishStreamMessage(key));
      return;
    }
    if (replayPersistedMessage(mergedMessage)) {
      return;
    }
    if (!isActiveConversation(message.conversationId)) return;
    updateMessagesForConversation(message.conversationId, (prev) =>
      upsertPersistedHistoryMessage(prev, mergedMessage),
    );
  };

  const finalizePendingStreams = (targetConversationId = conversationId) => {
    if (!targetConversationId) return;
    const pending = Array.from(streamingMessagesRef.current.entries()).filter(
      ([, message]) => message.conversationId === targetConversationId,
    );
    if (!pending.length) return;

    if (isActiveConversation(targetConversationId)) {
      // Keep the current visible streaming bubble in place for the active
      // conversation. `generation_finished` can arrive slightly earlier than
      // the persisted assistant message, and removing the bubble here caused a
      // blank gap until the user switched away and back.
      return;
    }

    setStreamingMessages((prev) => {
      const next = new Map(prev);
      pending.forEach(([key]) => {
        clearQueuedStream(key);
        clearQueuedThinking(key);
        pendingPersistedMessagesRef.current.delete(key);
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
          clearQueuedThinking(key);
          pendingPersistedMessagesRef.current.delete(key);
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

  const hasPendingConversationStreams = (
    targetConversationId = conversationId,
  ): boolean => {
    if (!targetConversationId) return false;
    for (const [key, message] of streamingMessagesRef.current.entries()) {
      if (message.conversationId !== targetConversationId) continue;
      if (tokenTimersRef.current.has(key) || thinkingTimersRef.current.has(key)) {
        return true;
      }
      if (tokenQueuesRef.current.get(key)?.length || thinkingQueuesRef.current.get(key)?.length) {
        return true;
      }
      if (
        pendingMessageEndPayloadsRef.current.has(key) ||
        pendingPersistedMessagesRef.current.has(key)
      ) {
        return true;
      }
    }
    return false;
  };

  const waitForConversationStreams = async (
    targetConversationId = conversationId,
    timeoutMs = 5000,
  ): Promise<void> => {
    if (!targetConversationId) return;
    const startedAt = Date.now();
    while (hasPendingConversationStreams(targetConversationId)) {
      if (Date.now() - startedAt >= timeoutMs) {
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 30));
    }
  };

  const streamHandlers: StreamAssistantHandlers = {
    onMessageStart: (payload) => {
      const agentId = agentIdentity(payload) || streamKey(payload);
      const key = scopedStreamKey(conversationId, payload);
      const existingKey = existingKeyForPayload(payload);
      const targetConversationId = conversationOf(conversationId, payload);
      const author = agentDisplayName(targetConversationId, agentId, payload);
      const agentAvatarUrl = payloadAgentAvatarUrl(payload);

      if (!agentId || !key) return;
      if (!streamingMessagesRef.current.has(existingKey || key)) {
        hiddenStreamKeysRef.current.delete(key);
      }

      setStreamingMessages((prev) => {
        const currentKey = prev.has(key) ? key : existingKey;
        if (currentKey && prev.has(currentKey)) {
          const existing = prev.get(currentKey);
          if (!existing) return prev;
          const next = new Map(prev);
          if (currentKey !== key) {
            next.delete(currentKey);
          }
          next.set(key, {
            ...existing,
            id: String(payload.agent_message_id || payload.message_id || existing.id),
            author,
            sender_avatar_url: agentAvatarUrl || existing.sender_avatar_url,
            rawContent: {
              ...(existing.rawContent || {}),
              agent_message_id: payload.agent_message_id || existing.rawContent?.agent_message_id,
              message_id: payload.message_id || existing.rawContent?.message_id,
              agent_id: payload.agent_id || existing.rawContent?.agent_id || agentId,
              agent_avatar_url: agentAvatarUrl || existing.rawContent?.agent_avatar_url,
              thinking_enabled:
                existing.rawContent?.thinking_enabled ??
                (payload.thinking_enabled === true),
              _streamThinkingEnabled:
                existing.rawContent?._streamThinkingEnabled ??
                existing.rawContent?.thinking_enabled ??
                (payload.thinking_enabled === true),
            },
          });
          streamingMessagesRef.current = next;
          return next;
        }

        const next = new Map(prev);
        const historyBoundaryIds = historyMessages
          .filter((message) => message.conversationId === targetConversationId)
          .map((message) => message.id);
        const msg = makeMessage({
          conversationId: targetConversationId,
          role: "assistant",
          kind: "text",
          author,
          content: "",
          sender_avatar_url: agentAvatarUrl,
          rawContent: {
            agent_message_id: payload.agent_message_id,
            message_id: payload.message_id,
            agent_id: payload.agent_id,
            agent_avatar_url: agentAvatarUrl,
            thinking_enabled:
              payload.thinking_enabled === true ||
              conversationThinkingMode.get(targetConversationId) === true,
            _streamRawText: "",
            _streamHistoryBoundaryIds: historyBoundaryIds,
            _streamThinkingEnabled:
              payload.thinking_enabled === true ||
              conversationThinkingMode.get(targetConversationId) === true,
          },
          streamState: "streaming",
          state: "active",
        });

        msg.id = String(payload.agent_message_id || payload.message_id || msg.id);
        next.set(key, msg);
        streamingMessagesRef.current = next;
        return next;
      });

      setDisplayOrder((prev) => {
        const withoutExisting =
          existingKey && existingKey !== key
            ? prev.filter((item) => item !== existingKey)
            : prev;
        return withoutExisting.includes(key) ? withoutExisting : [...withoutExisting, key];
      });
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
    onMessageNew: ingestPersistedMessage,
    onMessageUpdated: ingestPersistedMessage,
    onToolCallStart: (payload) => appendToolProgress(payload),
    onToolCallDone: () => {},
    onControl: () => {},
  };

  return {
    streamingMessages: activeStreamingMessages,
    displayOrder: activeDisplayOrder,
    streamHandlers,
    ingestPersistedMessages: (messages: ChatMessage[]) => {
      messages.forEach((message) => ingestPersistedMessage(message));
    },
    clearPendingStreams,
    hasPendingConversationStreams,
    waitForConversationStreams,
  };
}
