import { create } from "zustand";
import type { ChatMessage } from "@/types";

interface MessageState {
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

export const useMessageStore = create<MessageState>((set, get) => ({
  historyMessages: [],
  messageCache: new Map(),
  messageVersions: new Map(),

  setMessages: (messages) =>
    set((state) => ({
      historyMessages: messages,
      messageVersions: withMessageVersions(state.messageVersions, messages),
    })),

  setMessagesForConversation: (conversationId, messages) =>
    set((state) => {
      const nextCache = new Map(state.messageCache);
      nextCache.set(conversationId, messages);
      return {
        historyMessages: messages,
        messageCache: nextCache,
        messageVersions: withMessageVersions(state.messageVersions, messages),
      };
    }),

  updateMessages: (updater) =>
    set((state) => {
      const nextMessages = updater(state.historyMessages);
      const conversationId = nextMessages[0]?.conversationId;
      if (!conversationId) {
        return { historyMessages: nextMessages };
      }
      const nextCache = new Map(state.messageCache);
      nextCache.set(conversationId, nextMessages);
      return {
        historyMessages: nextMessages,
        messageCache: nextCache,
      };
    }),

  updateMessageVersions: (updater) =>
    set((state) => ({ messageVersions: updater(state.messageVersions) })),

  getMessageVersion: (messageId) => get().messageVersions.get(messageId) ?? 0,

  getCachedMessages: (conversationId) => get().messageCache.get(conversationId),

  setMessageVersions: (versions) => set({ messageVersions: versions }),

  clearMessages: () => set({ historyMessages: [], messageVersions: new Map() }),

  clearMessageCache: () => set({ messageCache: new Map() }),
}));
