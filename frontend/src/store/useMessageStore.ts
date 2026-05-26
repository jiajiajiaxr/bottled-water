import { create } from "zustand";
import type { ChatMessage } from "@/types";

export type StreamState = "idle" | "streaming" | "done" | "error";

interface MessageState {
  /** 历史消息：已完成的对话，Immutable */
  historyMessages: ChatMessage[];

  /** 流式消息：正在生成的回复，key 为消息 ID */
  streamingMessages: Map<string, ChatMessage>;

  streamState: StreamState;
  localRunningConversationIds: Set<string>;

  // === 历史消息操作 ===
  setHistoryMessages: (messages: ChatMessage[]) => void;
  appendHistoryMessage: (message: ChatMessage) => void;
  updateHistoryMessage: (messageId: string, patch: Partial<ChatMessage>) => void;
  replaceHistoryMessage: (oldId: string, message: ChatMessage) => void;

  // === 流式消息操作（O(1) Map 操作）===
  startStreamingMessage: (message: ChatMessage) => void;
  updateStreamingContent: (messageId: string, content: string) => void;
  updateStreamingThinking: (messageId: string, thinking: string) => void;
  updateStreamingState: (messageId: string, patch: Partial<ChatMessage>) => void;
  finishStreamingMessage: (messageId: string) => void;
  removeStreamingMessage: (messageId: string) => void;
  finishAllStreamingMessages: () => void;

  // === 流式状态 ===
  setStreamState: (state: StreamState) => void;
  addRunningConversationId: (id: string) => void;
  removeRunningConversationId: (id: string) => void;
  clearMessages: () => void;
  getAllMessages: () => ChatMessage[];
  setLocalRunningConversationIds: (ids: Set<string>) => void;
  updateLocalRunningConversationIds: (
    updater: (current: Set<string>) => Set<string>,
  ) => void;
}

export const useMessageStore = create<MessageState>((set, get) => ({
  historyMessages: [],
  streamingMessages: new Map(),
  streamState: "idle",
  localRunningConversationIds: new Set(),

  // --- 历史消息操作 ---

  setHistoryMessages: (messages) => set({ historyMessages: messages }),

  appendHistoryMessage: (message) =>
    set((state) => ({
      historyMessages: [...state.historyMessages, message],
    })),

  updateHistoryMessage: (messageId, patch) =>
    set((state) => {
      const index = state.historyMessages.findIndex((m) => m.id === messageId);
      if (index === -1) return state;
      const next = [...state.historyMessages];
      next[index] = { ...next[index], ...patch };
      return { historyMessages: next };
    }),

  replaceHistoryMessage: (oldId, message) =>
    set((state) => {
      const index = state.historyMessages.findIndex((m) => m.id === oldId);
      if (index === -1) {
        return { historyMessages: [...state.historyMessages, message] };
      }
      const next = [...state.historyMessages];
      next[index] = message;
      return { historyMessages: next };
    }),

  // --- 流式消息操作（O(1) Map 操作）---

  startStreamingMessage: (message) =>
    set((state) => {
      const next = new Map(state.streamingMessages);
      next.set(message.id, { ...message, streamState: "streaming" as const });
      return { streamingMessages: next };
    }),

  updateStreamingContent: (messageId, content) =>
    set((state) => {
      const msg = state.streamingMessages.get(messageId);
      if (!msg || msg.content === content) return state;
      const next = new Map(state.streamingMessages);
      next.set(messageId, { ...msg, content });
      return { streamingMessages: next };
    }),

  updateStreamingThinking: (messageId, thinking) =>
    set((state) => {
      const msg = state.streamingMessages.get(messageId);
      console.log("[store] updateStreamingThinking msgId=", messageId, "found=", !!msg, "currentThinking=", msg?.thinking, "newThinking=", thinking.slice(0, 30));
      if (!msg || msg.thinking === thinking) return state;
      const next = new Map(state.streamingMessages);
      next.set(messageId, { ...msg, thinking });
      console.log("[store] updated, streamingMessages keys=", Array.from(next.keys()));
      return { streamingMessages: next };
    }),

  updateStreamingState: (messageId, patch) =>
    set((state) => {
      const msg = state.streamingMessages.get(messageId);
      if (!msg) return state;
      const next = new Map(state.streamingMessages);
      next.set(messageId, { ...msg, ...patch });
      return { streamingMessages: next };
    }),

  finishStreamingMessage: (messageId) =>
    set((state) => {
      const msg = state.streamingMessages.get(messageId);
      if (!msg) return state;
      const nextStreaming = new Map(state.streamingMessages);
      nextStreaming.delete(messageId);
      return {
        historyMessages: [
          ...state.historyMessages,
          { ...msg, streamState: "done" as const },
        ],
        streamingMessages: nextStreaming,
      };
    }),

  removeStreamingMessage: (messageId) =>
    set((state) => {
      if (!state.streamingMessages.has(messageId)) return state;
      const next = new Map(state.streamingMessages);
      next.delete(messageId);
      return { streamingMessages: next };
    }),

  finishAllStreamingMessages: () =>
    set((state) => {
      if (!state.streamingMessages.size) return state;
      const doneMessages = Array.from(state.streamingMessages.values()).map(
        (msg) => ({ ...msg, streamState: "done" as const }),
      );
      return {
        historyMessages: [...state.historyMessages, ...doneMessages],
        streamingMessages: new Map(),
      };
    }),

  // --- 流式状态 ---

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

  clearMessages: () =>
    set({ historyMessages: [], streamingMessages: new Map() }),

  getAllMessages: () => {
    const { historyMessages, streamingMessages } = get();
    const streaming = Array.from(streamingMessages.values());
    return [...historyMessages, ...streaming].sort(
      (a, b) =>
        new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    );
  },

  setLocalRunningConversationIds: (localRunningConversationIds) =>
    set({ localRunningConversationIds }),

  updateLocalRunningConversationIds: (updater) =>
    set((state) => ({
      localRunningConversationIds: updater(state.localRunningConversationIds),
    })),
}));
