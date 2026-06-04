import { create } from "zustand";
import type { Conversation } from "@/types";

function loadThinkingEnabled(): Map<string, boolean> {
  if (typeof window === "undefined") {
    return new Map();
  }
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
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(
      "agenthub:thinking-enabled",
      JSON.stringify(Array.from(map.entries())),
    );
  } catch {
    // ignore
  }
}

function loadSelectedModelConfigIds(): Map<string, string> {
  if (typeof window === "undefined") {
    return new Map();
  }
  try {
    const raw = window.localStorage.getItem("agenthub:conversation-model-config");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        return new Map(parsed as [string, string][]);
      }
    }
  } catch {
    // ignore
  }
  return new Map();
}

function saveSelectedModelConfigIds(map: Map<string, string>) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(
      "agenthub:conversation-model-config",
      JSON.stringify(Array.from(map.entries())),
    );
  } catch {
    // ignore
  }
}

interface ConversationState {
  conversations: Conversation[];
  activeId: string | undefined;
  activeConversation: Conversation | undefined;
  conversationCategories: string[];
  isLoading: boolean;
  loadingMessages: boolean;

  setConversations: (conversations: Conversation[]) => void;
  setActiveId: (id: string | undefined) => void;
  setActiveConversation: (id: string) => void;
  updateActiveConversation: (patch: Partial<Conversation>) => void;
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

  selectedModelConfigIds: Map<string, string>;
  setSelectedModelConfigId: (
    conversationId: string,
    modelConfigId: string | undefined,
  ) => void;
  getSelectedModelConfigId: (conversationId: string) => string | undefined;
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  conversations: [],
  activeId: undefined,
  activeConversation: undefined,
  conversationCategories: [],
  isLoading: false,
  loadingMessages: false,
  thinkingEnabled: loadThinkingEnabled(),
  selectedModelConfigIds: loadSelectedModelConfigIds(),
  localRunningConversationIds: new Set(),

  setConversations: (conversations) => set({ conversations }),
  setActiveId: (id) => {
    const conversation = id ? get().conversations.find((item) => item.id === id) : undefined;
    set({ activeId: id, activeConversation: conversation });
  },
  setActiveConversation: (id) => {
    const conversation = get().conversations.find((item) => item.id === id);
    set({ activeId: id, activeConversation: conversation });
  },
  updateActiveConversation: (patch) => {
    const conversation = get().activeConversation;
    if (conversation) {
      const updated = { ...conversation, ...patch };
      set({
        activeConversation: updated,
        conversations: get().conversations.map((c) =>
          c.id === conversation.id ? updated : c,
        ),
      });
    }
  },
  setConversationCategories: (conversationCategories) =>
    set({ conversationCategories }),
  updateConversation: (id, patch) =>
    set((state) => {
      const conversations = state.conversations.map((c) =>
        c.id === id ? { ...c, ...patch } : c,
      );
      const activeConversation =
        state.activeConversation?.id === id
          ? { ...state.activeConversation, ...patch }
          : state.activeConversation;
      return { conversations, activeConversation };
    }),
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

  setSelectedModelConfigId: (conversationId, modelConfigId) =>
    set((state) => {
      const next = new Map(state.selectedModelConfigIds);
      if (modelConfigId === undefined) {
        next.delete(conversationId);
      } else {
        next.set(conversationId, modelConfigId);
      }
      saveSelectedModelConfigIds(next);
      return { selectedModelConfigIds: next };
    }),

  getSelectedModelConfigId: (conversationId) =>
    get().selectedModelConfigIds.get(conversationId),
}));
