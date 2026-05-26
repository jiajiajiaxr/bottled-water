import { useCallback, useEffect, useMemo } from "react";
import { useConversationStore } from "@/store";
import type { Conversation } from "@/types";
import {
  CONVERSATION_CATEGORY_OPTIONS,
  LEGACY_DEFAULT_CONVERSATION_CATEGORIES,
  mergeConversationCategories,
} from "@/lib/conversation";

export function useConversationCategories(
  activeWorkspaceId: string | undefined,
  conversations: Conversation[],
) {
  const {
    conversationCategories,
    setConversationCategories,
  } = useConversationStore();

  const storageKey = useMemo(
    () => `agenthub:conversation-categories:${activeWorkspaceId ?? "default"}`,
    [activeWorkspaceId],
  );

  const namesFromConversations = useMemo(
    () =>
      conversations.map((item) => item.folder || item.category || "Default"),
    [conversations],
  );

  const saveCategories = useCallback(
    (nextCategories: string[]) => {
      const merged = mergeConversationCategories(
        CONVERSATION_CATEGORY_OPTIONS,
        nextCategories,
      );
      setConversationCategories(merged);
      window.localStorage.setItem(
        storageKey,
        JSON.stringify({ version: 2, items: merged }),
      );
    },
    [storageKey, setConversationCategories],
  );

  const addCategory = useCallback(
    (name: string) => {
      saveCategories([...conversationCategories, name]);
    },
    [conversationCategories, saveCategories],
  );

  // Load from localStorage on mount / workspace change
  useEffect(() => {
    let stored: string[] = [];
    try {
      const raw = window.localStorage.getItem(storageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      if (Array.isArray(parsed)) {
        stored = parsed
          .map(String)
          .filter((name) => !LEGACY_DEFAULT_CONVERSATION_CATEGORIES.has(name));
      } else if (parsed && Array.isArray(parsed.items)) {
        stored = parsed.items.map(String);
      }
    } catch {
      stored = [];
    }
    setConversationCategories(
      mergeConversationCategories(CONVERSATION_CATEGORY_OPTIONS, stored),
    );
  }, [storageKey, setConversationCategories]);

  // Merge categories from conversations
  useEffect(() => {
    setConversationCategories(
      mergeConversationCategories(
        CONVERSATION_CATEGORY_OPTIONS,
        conversationCategories,
        namesFromConversations,
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [namesFromConversations]);

  return {
    conversationCategories,
    addCategory,
    saveCategories,
  };
}
