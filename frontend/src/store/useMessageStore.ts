import { create } from "zustand";
import type { ChatMessage } from "@/types";

interface MessageState {
  /** 当前对话的历史消息 */
  historyMessages: ChatMessage[];

  /** 消息版本号，用于 MessageBubble memo 优化 */
  messageVersions: Map<string, number>;

  // === 基础 setter ===
  setMessages: (messages: ChatMessage[]) => void;
  setMessageVersions: (versions: Map<string, number>) => void;

  // === 基于前状态的 updater ===
  updateMessages: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void;
  updateMessageVersions: (
    updater: (prev: Map<string, number>) => Map<string, number>,
  ) => void;

  // === 查询 ===
  getMessageVersion: (messageId: string) => number;

  // === 清理 ===
  clearMessages: () => void;
}

export const useMessageStore = create<MessageState>((set, get) => ({
  historyMessages: [],
  messageVersions: new Map(),

  setMessages: (messages) =>
    set((state) => {
      const nextVersions = new Map(state.messageVersions);
      for (const msg of messages) {
        if (!nextVersions.has(msg.id)) {
          nextVersions.set(msg.id, 0);
        }
      }
      return { historyMessages: messages, messageVersions: nextVersions };
    }),

  updateMessages: (updater) =>
    set((state) => ({ historyMessages: updater(state.historyMessages) })),

  updateMessageVersions: (updater) =>
    set((state) => ({ messageVersions: updater(state.messageVersions) })),

  getMessageVersion: (messageId) => get().messageVersions.get(messageId) ?? 0,

  setMessageVersions: (versions) => set({ messageVersions: versions }),

  clearMessages: () => set({ historyMessages: [], messageVersions: new Map() }),
}));
