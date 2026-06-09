import type { ChatMessage, ToolEventRecord } from "../types";

const FAILED_STATUSES = new Set(["failed", "error", "cancelled", "timeout"]);

export interface ToolSummary {
  label: string;
  tone: "normal" | "warning";
  details: ToolEventRecord[];
}

export function toolEventsFromMessage(message: ChatMessage): ToolEventRecord[] {
  return mergeToolEvents(
    message.toolEvents ?? [],
    readToolEvents(message.rawContent?.tool_events),
    readToolEvents(message.rawContent?.toolEvents),
    readToolEvents(message.rawContent?._toolEvents),
  );
}

export function mergeToolEvents(
  ...groups: ToolEventRecord[][]
): ToolEventRecord[] {
  const byKey = new Map<string, ToolEventRecord>();
  groups.flat().forEach((event, index) => {
    if (!event.toolName) return;
    const key =
      event.toolCallId || event.run_id || `${event.toolName}:${event.status || ""}:${index}`;
    byKey.set(key, { ...(byKey.get(key) ?? {}), ...event });
  });
  return Array.from(byKey.values());
}

export function summarizeToolEvents(
  events: ToolEventRecord[],
): ToolSummary | undefined {
  const completed = events.filter(
    (event) => String(event.status || "").toLowerCase() !== "running",
  );
  if (!completed.length) return undefined;
  const finalFailed = finalFailedToolEvents(completed);
  if (finalFailed.length) {
    return {
      label: `工具失败：${formatToolNames(finalFailed, 3).text}`,
      tone: "warning",
      details: completed,
    };
  }
  return {
    label: `调用：${formatToolNames(completed, 3).text}`,
    tone: "normal",
    details: completed,
  };
}

export function isFailedToolEvent(event: ToolEventRecord) {
  const status = String(event.status || "").toLowerCase();
  if (event.toolName === "terminal.wait_for" && status === "timeout") {
    return false;
  }
  if (FAILED_STATUSES.has(status)) return true;
  if (status === "succeeded" || status === "completed") return false;
  const exitCode = Number(event.exit_code);
  if (Number.isFinite(exitCode) && exitCode !== 0) return true;
  return Boolean(event.error);
}

export function toolEventDetailLines(event: ToolEventRecord): string[] {
  return [
    `tool: ${event.toolName}`,
    event.provider ? `provider: ${event.provider}` : "",
    event.run_id ? `run_id: ${event.run_id}` : "",
    `status: ${event.status || "unknown"}`,
    event.changed_files_count !== undefined
      ? `changed_files: ${event.changed_files_count}`
      : "",
    event.exit_code !== undefined ? `exit_code: ${event.exit_code}` : "",
    event.duration_ms !== undefined ? `duration_ms: ${event.duration_ms}` : "",
    event.stdout ? `stdout: ${shortText(event.stdout)}` : "",
    event.stderr ? `stderr: ${shortText(event.stderr)}` : "",
    event.error ? `error: ${shortText(event.error)}` : "",
    event.summary ? `summary: ${shortText(event.summary)}` : "",
  ].filter(Boolean);
}

function readToolEvents(value: unknown): ToolEventRecord[] {
  if (!Array.isArray(value)) return [];
  return value.map(normalizeToolEvent).filter((event) => Boolean(event.toolName));
}

function normalizeToolEvent(value: unknown): ToolEventRecord {
  if (!value || typeof value !== "object") return { toolName: "" };
  const record = value as Record<string, unknown>;
  return {
    toolName: stringValue(record.toolName ?? record.tool_name),
    toolCallId: stringValue(record.toolCallId ?? record.tool_call_id),
    run_id: stringValue(record.run_id ?? record.runId),
    provider: stringValue(record.provider),
    changed_files_count: primitiveValue(
      record.changed_files_count ?? record.changedFilesCount,
    ),
    status: stringValue(record.status),
    exit_code: primitiveValue(record.exit_code ?? record.exitCode),
    duration_ms: primitiveValue(record.duration_ms ?? record.durationMs),
    stdout: stringValue(record.stdout ?? record.stdout_tail ?? record.stdoutTail),
    stderr: stringValue(record.stderr ?? record.stderr_tail ?? record.stderrTail),
    summary: stringValue(record.summary ?? record.session_status ?? record.sessionStatus),
    error: stringValue(record.error ?? record.error_message),
    session_id: stringValue(record.session_id ?? record.sessionId),
    session_status: stringValue(record.session_status ?? record.sessionStatus),
    command: stringValue(record.command),
    cwd: stringValue(record.cwd),
  };
}

function finalFailedToolEvents(events: ToolEventRecord[]) {
  const latestByTool = new Map<string, ToolEventRecord>();
  events.forEach((event) => latestByTool.set(event.toolName, event));
  return Array.from(latestByTool.values()).filter(isFailedToolEvent);
}

function formatToolNames(events: ToolEventRecord[], maxTools: number) {
  const counts = new Map<string, number>();
  events.forEach((event) => {
    counts.set(event.toolName, (counts.get(event.toolName) ?? 0) + 1);
  });
  const names = Array.from(counts.entries());
  const visible = names.slice(0, maxTools).map(([name, count]) =>
    count > 1 ? `${name} ×${count}` : name,
  );
  const hiddenCount = names
    .slice(maxTools)
    .reduce((sum, [, count]) => sum + count, 0);
  return {
    text: hiddenCount
      ? `${visible.join(" · ")} · 等 ${hiddenCount} 项`
      : visible.join(" · "),
  };
}

function primitiveValue(value: unknown) {
  return typeof value === "string" || typeof value === "number"
    ? value
    : undefined;
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function shortText(value: string, limit = 160) {
  const text = value.replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}
