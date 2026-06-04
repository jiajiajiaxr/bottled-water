import type {
  ChatMessage,
  Conversation,
  MessageAttachment,
} from "@/types";

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
  const internalFenceResult = stripInternalFencedBlocks(text);
  const lines = internalFenceResult.text.split(/\r?\n/);
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
  return cleaned || (
    sawInternal || internalFenceResult.removed ? "" : text.trim()
  );
}

function stripInternalFencedBlocks(text: string) {
  const lines = text.split(/\r?\n/);
  const visible: string[] = [];
  let skippingFence = false;
  let removed = false;
  const statusFence = "```status_report";
  const statusFenceNames = ["status_report", "status"];
  const canBecomeStatusFence = (value: string) =>
    Boolean(value) &&
    (statusFence.startsWith(value) ||
      /^```\s*(?:status_report|status)\b/i.test(value) ||
      (() => {
        const partial = value.match(/^```\s*([a-z_]*)$/i);
        if (!partial) return false;
        return statusFenceNames.some((name) =>
          name.startsWith(partial[1].toLowerCase()),
        );
      })());

  for (const [index, line] of lines.entries()) {
    const trimmed = line.trim();
    const lowered = trimmed.toLowerCase();

    if (!skippingFence && /^```\s*status_report\b/i.test(trimmed)) {
      skippingFence = true;
      removed = true;
      continue;
    }

    if (skippingFence) {
      if (trimmed.startsWith("```")) skippingFence = false;
      continue;
    }

    if (index === lines.length - 1 && canBecomeStatusFence(lowered)) {
      removed = true;
      continue;
    }

    if (lowered === "```" && index === lines.length - 1) {
      removed = true;
      continue;
    }

    if (
      lowered.startsWith("```") &&
      lowered !== "```" &&
      statusFence.startsWith(lowered)
    ) {
      skippingFence = true;
      removed = true;
      continue;
    }

    visible.push(line);
  }

  return { text: visible.join("\n"), removed };
}

export function isTaskRunning(status?: string) {
  return RUNNING_TASK_STATUSES.has(String(status || "").toUpperCase());
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

export function isSuccessfulToolRunnerMessage(message: ChatMessage) {
  const author = String(message.author || "").toLowerCase();
  const raw = message.rawContent || {};
  const output = (raw.output || raw.result || {}) as Record<string, unknown>;
  const hasToolName = Boolean(raw.tool_name || raw.toolName || output.tool_name || output.toolName);
  const looksLikeToolRunner =
    message.role === "tool" ||
    author === "tool runner" ||
    author.includes("tool runner") ||
    hasToolName;
  if (!looksLikeToolRunner) return false;

  const status = String(raw.status || output.status || "").toLowerCase();
  if (["failed", "error", "cancelled", "timeout"].includes(status)) return false;
  if (["succeeded", "success", "completed", "ok"].includes(status)) return true;

  const exitCode = Number(output.exit_code ?? output.exitCode ?? raw.exit_code ?? raw.exitCode);
  if (Number.isFinite(exitCode)) return exitCode === 0;

  if (output.error || raw.error) return false;
  return hasToolName && Boolean(output.stdout || output.summary || output.result);
}

export function isVisibleChatMessage(message: ChatMessage) {
  return !isSuccessfulToolRunnerMessage(message);
}

export function participantName(
  item: Conversation["participants"][number],
) {
  return item.agent_name || item.nickname || item.user_id || "成员";
}
