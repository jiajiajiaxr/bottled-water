export const CONVERSATION_CATEGORY_OPTIONS = ["Default"];

export const LEGACY_DEFAULT_CONVERSATION_CATEGORIES = new Set([
  "工厂",
  "字节跳动",
  "项目",
  "个人",
  "Demo",
  "归档整理",
  "Factory",
]);

export function normalizeConversationCategory(value?: string) {
  const name = value?.trim();
  return name || "Default";
}

export function mergeConversationCategories(
  ...groups: Array<Array<string | undefined>>
) {
  return Array.from(
    new Set(
      groups
        .flat()
        .map((name) => normalizeConversationCategory(name))
        .filter(Boolean),
    ),
  );
}
