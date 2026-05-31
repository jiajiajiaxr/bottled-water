const MAIN_TABS = new Set(["chat", "agents", "workspace", "settings"]);

export function normalizeMainTab(
  value: string | null,
): "chat" | "agents" | "workspace" | "settings" {
  return MAIN_TABS.has(value ?? "")
    ? (value as "chat" | "agents" | "workspace" | "settings")
    : "chat";
}
