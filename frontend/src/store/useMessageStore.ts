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
  updateMessageContent: (messageId: string, content: string) => void;
  updateMessageThinking: (messageId: string, thinking: string) => void;
  setStreamState: (state: StreamState) => void;
  addRunningConversationId: (id: string) => void;
  removeRunningConversationId: (id: string) => void;
  clearMessages: () => void;
  updateMessages: (updater: (current: ChatMessage[]) => ChatMessage[]) => void;
  setLocalRunningConversationIds: (ids: Set<string>) => void;
  updateLocalRunningConversationIds: (
    updater: (current: Set<string>) => Set<string>,
  ) => void;
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
    set((state) => {
      const index = state.messages.findIndex((m) => m.id === messageId);
      if (index === -1) return state;
      const next = [...state.messages];
      next[index] = { ...next[index], ...patch };
      return { messages: next };
    }),
  updateMessageContent: (messageId, content) =>
    set((state) => {
      const index = state.messages.findIndex((m) => m.id === messageId);
      if (index === -1) return state;
      const target = state.messages[index];
      if (target.content === content) return state;
      const next = [...state.messages];
      next[index] = { ...target, content };
      return { messages: next };
    }),
  updateMessageThinking: (messageId, thinking) =>
    set((state) => {
      const index = state.messages.findIndex((m) => m.id === messageId);
      if (index === -1) return state;
      const target = state.messages[index];
      if (target.thinking === thinking) return state;
      const next = [...state.messages];
      next[index] = { ...target, thinking };
      return { messages: next };
    }),
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
  updateMessages: (updater) =>
    set((state) => ({ messages: updater(state.messages) })),
  setLocalRunningConversationIds: (localRunningConversationIds) =>
    set({ localRunningConversationIds }),
  updateLocalRunningConversationIds: (updater) =>
    set((state) => ({
      localRunningConversationIds: updater(
        state.localRunningConversationIds,
      ),
    })),
}));
