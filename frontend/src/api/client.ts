import type { ChatMessage } from "../types";

export const API_BASE = "/api/v1";

export function unwrap<T>(payload: unknown): T {
  if (
    payload &&
    typeof payload === "object" &&
    "code" in payload &&
    "data" in payload
  ) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = window.localStorage.getItem("agenthub_token");
  const isForm = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.clone().json();
      detail = payload?.message || payload?.detail || payload?.error || detail;
    } catch {
      try {
        detail = await response.clone().text();
      } catch {
        detail = response.statusText;
      }
    }
    throw new Error(`${response.status} ${detail}`);
  }

  return unwrap<T>(await response.json());
}

export async function requestWithTimeout<T>(
  path: string,
  init: RequestInit,
  timeoutMs = 7000,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await request<T>(path, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

export async function requestFile(
  path: string,
): Promise<{
  previewUrl?: string;
  previewText?: string;
  contentType: string;
  filename?: string;
}> {
  const token = window.localStorage.getItem("agenthub_token");
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  const contentType =
    response.headers.get("content-type") ?? "application/octet-stream";
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = /filename="?([^";]+)"?/i.exec(disposition)?.[1];

  if (
    contentType.startsWith("text/") ||
    contentType.includes("json") ||
    contentType.includes("xml")
  ) {
    return { previewText: await response.text(), contentType, filename };
  }

  return {
    previewUrl: URL.createObjectURL(await response.blob()),
    contentType,
    filename,
  };
}

export const wait = (ms: number) =>
  new Promise((resolve) => window.setTimeout(resolve, ms));

export type StreamAssistantHandlers = {
  onDelta?: (delta: string, payload: Record<string, unknown>) => void;
  onReasoningDelta?: (delta: string, payload: Record<string, unknown>) => void;
  onMessageStart?: (payload: Record<string, unknown>) => void;
  onMessageUpdated?: (message: ChatMessage) => void;
  onMessageNew?: (message: ChatMessage) => void;
  onToolCallStart?: (payload: Record<string, unknown>) => void;
  onToolCallDone?: (payload: Record<string, unknown>) => void;
  onDone?: (payload?: Record<string, unknown>) => void;
  onControl?: (stop: () => void) => void;
};

export function eventPayload(event: Event): Record<string, unknown> {
  try {
    const value = JSON.parse((event as MessageEvent).data);
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}
