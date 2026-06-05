export type MainTab = "chat" | "agents" | "workspace" | "settings" | "files";

const MAIN_TABS = new Set(["chat", "agents", "workspace", "settings", "files"]);

export function normalizeMainTab(
  value: string | null,
): MainTab {
  return MAIN_TABS.has(value ?? "")
    ? (value as MainTab)
    : "chat";
}
