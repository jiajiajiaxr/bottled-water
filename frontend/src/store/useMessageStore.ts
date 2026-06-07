import { create } from "zustand";
import type { ChatMessage } from "@/types";

interface MessageState {
  /** historyMessages 当前对应的会话。 */
  historyConversationId: string | undefined;

  /** 当前会话的历史消息。 */
  historyMessages: ChatMessage[];

  /** 按会话缓存历史消息，减少来回切换会话时的空白和重复渲染。 */
  messageCache: Map<string, ChatMessage[]>;

  /** 消息版本号，用于 MessageBubble memo 优化。 */
  messageVersions: Map<string, number>;

  setMessages: (messages: ChatMessage[]) => void;
  setMessagesForConversation: (
    conversationId: string,
    messages: ChatMessage[],
  ) => void;
  setMessageVersions: (versions: Map<string, number>) => void;

  updateMessages: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
  updateMessagesForConversation: (
    conversationId: string,
    updater: (prev: ChatMessage[]) => ChatMessage[],
  ) => void;
  updateMessageVersions: (
    updater: (prev: Map<string, number>) => Map<string, number>,
  ) => void;

  getMessageVersion: (messageId: string) => number;
  getCachedMessages: (conversationId: string) => ChatMessage[] | undefined;

  clearMessages: () => void;
  clearMessageCache: () => void;
}

function withMessageVersions(
  current: Map<string, number>,
  messages: ChatMessage[],
) {
  const nextVersions = new Map(current);
  for (const msg of messages) {
    if (!nextVersions.has(msg.id)) {
      nextVersions.set(msg.id, 0);
    }
  }
  return nextVersions;
}

function conversationIdOf(messages: ChatMessage[]): string | undefined {
  return messages.find((message) => message.conversationId)?.conversationId;
}

function scopedMessages(conversationId: string, messages: ChatMessage[]) {
  return messages.filter((message) => message.conversationId === conversationId);
}

export const useMessageStore = create<MessageState>((set, get) => ({
  historyConversationId: undefined,
  historyMessages: [],
  messageCache: new Map(),
  messageVersions: new Map(),

  setMessages: (messages) =>
    set((state) => {
      const conversationId = conversationIdOf(messages);
      const nextMessages = conversationId
        ? scopedMessages(conversationId, messages)
        : messages;
      const nextCache = new Map(state.messageCache);
      if (conversationId) {
        nextCache.set(conversationId, nextMessages);
      }
      return {
        historyConversationId: conversationId,
        historyMessages: nextMessages,
        messageCache: nextCache,
        messageVersions: withMessageVersions(state.messageVersions, nextMessages),
      };
    }),

  setMessagesForConversation: (conversationId, messages) =>
    set((state) => {
      const nextMessages = scopedMessages(conversationId, messages);
      const nextCache = new Map(state.messageCache);
      nextCache.set(conversationId, nextMessages);
      return {
        historyConversationId: conversationId,
        historyMessages: nextMessages,
        messageCache: nextCache,
        messageVersions: withMessageVersions(state.messageVersions, nextMessages),
      };
    }),

  updateMessages: (updater) =>
    set((state) => {
      const conversationId =
        state.historyConversationId ||
        conversationIdOf(state.historyMessages);
      const nextMessages = conversationId
        ? scopedMessages(conversationId, updater(state.historyMessages))
        : updater(state.historyMessages);
      if (!conversationId) {
        return { historyMessages: nextMessages };
      }
      const nextCache = new Map(state.messageCache);
      nextCache.set(conversationId, nextMessages);
      return {
        historyConversationId: conversationId,
        historyMessages: nextMessages,
        messageCache: nextCache,
        messageVersions: withMessageVersions(state.messageVersions, nextMessages),
      };
    }),

  updateMessagesForConversation: (conversationId, updater) =>
    set((state) => {
      const prevMessages =
        state.historyConversationId === conversationId
          ? state.historyMessages
          : state.messageCache.get(conversationId) ?? [];
      const nextMessages = scopedMessages(conversationId, updater(prevMessages));
      const nextCache = new Map(state.messageCache);
      nextCache.set(conversationId, nextMessages);
      const shouldUpdateHistory =
        !state.historyConversationId ||
        state.historyConversationId === conversationId;
      if (!shouldUpdateHistory) {
        return {
          messageCache: nextCache,
          messageVersions: withMessageVersions(state.messageVersions, nextMessages),
        };
      }
      return {
        historyConversationId: conversationId,
        historyMessages: nextMessages,
        messageCache: nextCache,
        messageVersions: withMessageVersions(state.messageVersions, nextMessages),
      };
    }),

  updateMessageVersions: (updater) =>
    set((state) => ({ messageVersions: updater(state.messageVersions) })),

  getMessageVersion: (messageId) => get().messageVersions.get(messageId) ?? 0,

  getCachedMessages: (conversationId) => {
    const cached = get().messageCache.get(conversationId);
    return cached ? scopedMessages(conversationId, cached) : undefined;
  },

  setMessageVersions: (versions) => set({ messageVersions: versions }),

  clearMessages: () =>
    set({
      historyConversationId: undefined,
      historyMessages: [],
      messageVersions: new Map(),
    }),

  clearMessageCache: () => set({ messageCache: new Map() }),
}));
