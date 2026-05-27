import { create } from "zustand";
import type { Conversation } from "@/types";

function loadThinkingEnabled(): Map<string, boolean> {
  try {
    const raw = window.localStorage.getItem("agenthub:thinking-enabled");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return new Map(parsed as [string, boolean][]);
      }
    }
  } catch {
    // ignore
  }
  return new Map();
}

function saveThinkingEnabled(map: Map<string, boolean>) {
  try {
    window.localStorage.setItem(
      "agenthub:thinking-enabled",
      JSON.stringify(Array.from(map.entries())),
    );
  } catch {
    // ignore
  }
}

interface ConversationState {
  conversations: Conversation[];
  currentConversationId: string | null;
  activeId: string | undefined;
  conversationCategories: string[];
  isLoading: boolean;
  loadingMessages: boolean;
  setConversations: (conversations: Conversation[]) => void;
  setCurrentConversationId: (id: string | null) => void;
  setActiveId: (id: string | undefined) => void;
  setConversationCategories: (categories: string[]) => void;
  updateConversation: (id: string, patch: Partial<Conversation>) => void;
  addConversation: (conversation: Conversation) => void;
  removeConversation: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setLoadingMessages: (loading: boolean) => void;
  updateConversations: (
    updater: (current: Conversation[]) => Conversation[],
  ) => void;

  // === 运行中对话标记 ===
  localRunningConversationIds: Set<string>;
  setLocalRunningConversationIds: (ids: Set<string>) => void;
  updateLocalRunningConversationIds: (
    updater: (current: Set<string>) => Set<string>,
  ) => void;

  // === 思考模式（按会话存储，参与持久化） ===
  thinkingEnabled: Map<string, boolean>;
  setThinkingEnabled: (conversationId: string, enabled: boolean) => void;
  getThinkingEnabled: (conversationId: string) => boolean;
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  currentConversationId: null,
  activeId: undefined,
  conversationCategories: [],
  isLoading: false,
  loadingMessages: false,
  thinkingEnabled: loadThinkingEnabled(),
  localRunningConversationIds: new Set(),

  setConversations: (conversations) => set({ conversations }),
  setCurrentConversationId: (id) => set({ currentConversationId: id }),
  setActiveId: (activeId) => set({ activeId }),
  setConversationCategories: (conversationCategories) =>
    set({ conversationCategories }),
  updateConversation: (id, patch) =>
    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === id ? { ...c, ...patch } : c,
      ),
    })),
  addConversation: (conversation) =>
    set((state) => ({
      conversations: [conversation, ...state.conversations],
    })),
  removeConversation: (id) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
    })),
  setLoading: (isLoading) => set({ isLoading }),
  setLoadingMessages: (loadingMessages) => set({ loadingMessages }),
  updateConversations: (updater) =>
    set((state) => ({ conversations: updater(state.conversations) })),

  // --- 运行中对话标记 ---

  setLocalRunningConversationIds: (ids) =>
    set({ localRunningConversationIds: ids }),

  updateLocalRunningConversationIds: (updater) =>
    set((state) => ({
      localRunningConversationIds: updater(state.localRunningConversationIds),
    })),

  // --- 思考模式（按会话持久化） ---

  setThinkingEnabled: (conversationId, enabled) =>
    set((state) => {
      const next = new Map(state.thinkingEnabled);
      next.set(conversationId, enabled);
      saveThinkingEnabled(next);
      return { thinkingEnabled: next };
    }),

  getThinkingEnabled: (conversationId) =>
    get().thinkingEnabled.get(conversationId) ?? false,
}));
