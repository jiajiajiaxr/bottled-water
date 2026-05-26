import { create } from "zustand";
import type { Conversation } from "@/types";

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
}

export const useConversationStore = create<ConversationState>((set) => ({
  conversations: [],
  currentConversationId: null,
  activeId: undefined,
  conversationCategories: [],
  isLoading: false,
  loadingMessages: false,
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
}));
