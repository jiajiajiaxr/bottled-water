import type {
  ChatMessage,
  Conversation,
  MessageAttachment,
} from "../types";

export function makeMessage(
  partial: Omit<ChatMessage, "id" | "createdAt">,
): ChatMessage {
  return {
    ...partial,
    id: `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    createdAt: new Date().toISOString(),
  };
}

export function messageAttachments(message: ChatMessage): MessageAttachment[] {
  const rawAttachments = message.rawContent?.attachments;
  const items = [
    ...(message.attachments ?? []),
    ...(Array.isArray(rawAttachments)
      ? (rawAttachments as MessageAttachment[])
      : []),
  ];
  const seen = new Set<string>();
  return items.filter((item) => {
    const key =
      item.file_id ?? item.id ?? item.filename ?? item.original_filename;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function attachmentName(file: MessageAttachment) {
  return (
    file.original_filename ?? file.filename ?? file.file_id ?? file.id ?? "附件"
  );
}

export const INTERNAL_SECTION_TITLES = new Set([
  "任务拆解",
  "执行过程",
  "合规审查",
]);

export const FINAL_SECTION_TITLES = new Set([
  "最终产物",
  "最终回答",
  "最终回复",
  "最终结果",
  "正式回复",
  "回复",
]);

export const RUNNING_TASK_STATUSES = new Set([
  "PENDING",
  "QUEUED",
  "EXECUTING",
  "RUNNING",
  "REVIEW_PENDING",
  "REVIEWING",
  "STREAMING",
]);

export function sectionTitle(line: string): { title?: string; remainder: string } {
  const clean = line
    .replace(/^\s*(?:#{1,6}\s*)?(?:\d+[.、)]\s*)?/, "")
    .trim()
    .replace(/^\*+|\*+$/g, "")
    .trim();
  if (!clean) return { remainder: "" };
  const separatorIndexes = [clean.indexOf("："), clean.indexOf(":")].filter(
    (index) => index >= 0,
  );
  const separatorIndex = separatorIndexes.length
    ? Math.min(...separatorIndexes)
    : -1;
  if (separatorIndex >= 0) {
    return {
      title: clean
        .slice(0, separatorIndex)
        .trim()
        .replace(/^\*+|\*+$/g, "")
        .trim(),
      remainder: clean.slice(separatorIndex + 1).trim(),
    };
  }
  return { title: clean, remainder: "" };
}

export function stripInternalAgentOutput(raw: string) {
  const text = String(raw || "");
  if (!text.trim()) return "";
  const lines = text.split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const { title, remainder } = sectionTitle(lines[index]);
    if (title && FINAL_SECTION_TITLES.has(title)) {
      return [remainder, ...lines.slice(index + 1)]
        .filter(Boolean)
        .join("\n")
        .trim();
    }
  }
  const visible: string[] = [];
  let skipping = false;
  let sawInternal = false;
  lines.forEach((line) => {
    const { title } = sectionTitle(line);
    if (title && INTERNAL_SECTION_TITLES.has(title)) {
      sawInternal = true;
      skipping = true;
      return;
    }
    if (title && !INTERNAL_SECTION_TITLES.has(title)) skipping = false;
    if (!skipping) visible.push(line);
  });
  const cleaned = visible.join("\n").trim();
  return cleaned || (sawInternal ? "" : text.trim());
}

export function isTaskRunning(status?: string) {
  return RUNNING_TASK_STATUSES.has(String(status || "").toUpperCase());
}

export function isSuccessfulToolRunnerMessage(message: ChatMessage) {
  if (message.author !== "Tool Runner") return false;
  const raw = message.rawContent ?? {};
  const output = raw.output;
  const outputRecord = output && typeof output === "object" ? (output as Record<string, unknown>) : {};
  const nestedResult =
    outputRecord.result && typeof outputRecord.result === "object"
      ? (outputRecord.result as Record<string, unknown>)
      : {};
  const outputStatus = String(outputRecord.status ?? nestedResult.status ?? "");
  const status = String(raw.status ?? outputStatus ?? message.status ?? "").toLowerCase();
  const hasError =
    Boolean(raw.error || raw.error_message) ||
    Boolean(outputRecord.error || outputRecord.error_message || nestedResult.error || nestedResult.error_message);
  return !hasError && !["failed", "error", "cancelled", "timeout"].includes(status);
}

export function isVisibleChatMessage(message: ChatMessage) {
  return !isSuccessfulToolRunnerMessage(message);
}

export function isLikelyArtifactRequest(text: string) {
  const value = text.toLowerCase();
  return [
    "word",
    "docx",
    "文档",
    "报告",
    "excel",
    "xlsx",
    "表格",
    "ppt",
    "幻灯片",
    "网页",
    "web",
    "html",
    "react",
    "预览",
    "部署",
    "代码",
    "项目",
  ].some((keyword) => value.includes(keyword));
}

export function participantName(
  item: Conversation["participants"][number],
) {
  return item.agent_name || item.nickname || item.user_id || "成员";
}
