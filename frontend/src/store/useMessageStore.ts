import { create } from "zustand";
import type { ChatMessage } from "../types";

interface MessageState {
  messages: Record<string, ChatMessage[]>;
  streamingConversationId: string | null;
  setMessages: (conversationId: string, messages: ChatMessage[]) => void;
  appendMessage: (conversationId: string, message: ChatMessage) => void;
  updateMessage: (
    conversationId: string,
    messageId: string,
    patch: Partial<ChatMessage>,
  ) => void;
  setStreamingConversationId: (id: string | null) => void;
  clearMessages: (conversationId: string) => void;
}

export const useMessageStore = create<MessageState>((set) => ({
  messages: {},
  streamingConversationId: null,
  setMessages: (conversationId, messages) =>
    set((state) => ({
      messages: { ...state.messages, [conversationId]: messages },
    })),
  appendMessage: (conversationId, message) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: [
          ...(state.messages[conversationId] ?? []),
          message,
        ],
      },
    })),
  updateMessage: (conversationId, messageId, patch) =>
    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
          m.id === messageId ? { ...m, ...patch } : m,
        ),
      },
    })),
  setStreamingConversationId: (id) => set({ streamingConversationId: id }),
  clearMessages: (conversationId) =>
    set((state) => {
      const next = { ...state.messages };
      delete next[conversationId];
      return { messages: next };
    }),
}));
