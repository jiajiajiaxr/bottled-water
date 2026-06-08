import { create } from "zustand";
import type { Conversation } from "@/types";

function sameStringArray(left: string[], right: string[]) {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function sameStringSet(left: Set<string>, right: Set<string>) {
  if (left.size !== right.size) return false;
  for (const item of left) {
    if (!right.has(item)) return false;
  }
  return true;
}

function sameConversationPatch(
  conversation: Conversation | undefined,
  patch: Partial<Conversation>,
) {
  if (!conversation) return false;
  const keys = Object.keys(patch) as (keyof Conversation)[];
  return keys.length > 0 && keys.every((key) => Object.is(conversation[key], patch[key]));
}

function sameConversationArray(left: Conversation[], right: Conversation[]) {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

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

  draftSnippets: Map<string, string>;
  appendDraftSnippet: (conversationId: string, snippet: string) => void;
  consumeDraftSnippet: (conversationId: string) => string;
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
  draftSnippets: new Map(),
  localRunningConversationIds: new Set(),

  setConversations: (conversations) =>
    set((state) =>
      sameConversationArray(state.conversations, conversations)
        ? state
        : { conversations },
    ),
  setActiveId: (id) => {
    set((state) => {
      const conversation = id ? state.conversations.find((item) => item.id === id) : undefined;
      return state.activeId === id && state.activeConversation === conversation
        ? state
        : { activeId: id, activeConversation: conversation };
    });
  },
  setActiveConversation: (id) => {
    set((state) => {
      const conversation = state.conversations.find((item) => item.id === id);
      return state.activeId === id && state.activeConversation === conversation
        ? state
        : { activeId: id, activeConversation: conversation };
    });
  },
  updateActiveConversation: (patch) => {
    const conversation = get().activeConversation;
    if (conversation) {
      if (sameConversationPatch(conversation, patch)) return;
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
    set((state) =>
      sameStringArray(state.conversationCategories, conversationCategories)
        ? state
        : { conversationCategories },
    ),
  updateConversation: (id, patch) =>
    set((state) => {
      const current = state.conversations.find((item) => item.id === id);
      const activeCurrent =
        state.activeConversation?.id === id ? state.activeConversation : undefined;
      if (!current && !activeCurrent) return state;
      if (
        sameConversationPatch(current, patch) &&
        (!activeCurrent || sameConversationPatch(activeCurrent, patch))
      ) {
        return state;
      }
      const updated = current ? { ...current, ...patch } : undefined;
      const activeUpdated = activeCurrent ? { ...activeCurrent, ...patch } : state.activeConversation;
      const conversations = updated
        ? state.conversations.map((c) => (c.id === id ? updated : c))
        : state.conversations;
      const activeConversation =
        state.activeConversation?.id === id ? activeUpdated : state.activeConversation;
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
    set((state) => {
      const conversations = updater(state.conversations);
      return sameConversationArray(state.conversations, conversations)
        ? state
        : { conversations };
    }),

  // --- 运行中对话标记 ---

  setLocalRunningConversationIds: (ids) =>
    set((state) =>
      sameStringSet(state.localRunningConversationIds, ids)
        ? state
        : { localRunningConversationIds: ids },
    ),

  updateLocalRunningConversationIds: (updater) =>
    set((state) => {
      const next = updater(state.localRunningConversationIds);
      return sameStringSet(state.localRunningConversationIds, next)
        ? state
        : { localRunningConversationIds: next };
    }),

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

  appendDraftSnippet: (conversationId, snippet) =>
    set((state) => {
      const next = new Map(state.draftSnippets);
      next.set(conversationId, `${next.get(conversationId) ?? ""}${snippet}`);
      return { draftSnippets: next };
    }),

  consumeDraftSnippet: (conversationId) => {
    const value = get().draftSnippets.get(conversationId) ?? "";
    if (!value) return "";
    set((state) => {
      const next = new Map(state.draftSnippets);
      next.delete(conversationId);
      return { draftSnippets: next };
    });
    return value;
  },
}));
