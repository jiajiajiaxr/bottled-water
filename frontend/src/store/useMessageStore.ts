import { create } from "zustand";
import type { ChatMessage } from "../types";

export type StreamState = "idle" | "streaming" | "done" | "error";

interface MessageState {
  messages: ChatMessage[];
  streamState: StreamState;
  localRunningConversationIds: Set<string>;
  setMessages: (messages: ChatMessage[]) => void;
  appendMessage: (message: ChatMessage) => void;
  updateMessage: (messageId: string, patch: Partial<ChatMessage>) => void;
  setStreamState: (state: StreamState) => void;
  addRunningConversationId: (id: string) => void;
  removeRunningConversationId: (id: string) => void;
  clearMessages: () => void;
}

export const useMessageStore = create<MessageState>((set) => ({
  messages: [],
  streamState: "idle",
  localRunningConversationIds: new Set(),
  setMessages: (messages) => set({ messages }),
  appendMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
  updateMessage: (messageId, patch) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId ? { ...m, ...patch } : m,
      ),
    })),
  setStreamState: (streamState) => set({ streamState }),
  addRunningConversationId: (id) =>
    set((state) => {
      const next = new Set(state.localRunningConversationIds);
      next.add(id);
      return { localRunningConversationIds: next };
    }),
  removeRunningConversationId: (id) =>
    set((state) => {
      const next = new Set(state.localRunningConversationIds);
      next.delete(id);
      return { localRunningConversationIds: next };
    }),
  clearMessages: () => set({ messages: [] }),
}));
