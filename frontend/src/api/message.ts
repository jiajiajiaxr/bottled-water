import { StreamAssistantHandlers } from "@/types/messages";
import { get, post, sse } from "./client";
import type { ChatMessage } from "@/types";

export async function messages(conversationId: string): Promise<ChatMessage[]> {
  const result = await get<{ items: ChatMessage[] } | ChatMessage[]>(
    `/conversations/${conversationId}/messages`,
  );

  return Array.isArray(result) ? result : result.items;
}

/**
 * 解析 SSE 流，逐条产出 {event, data}。
 * SSE 格式：event: xxx\ndata: {...}\n\n
 */
interface SSEEvent {
  id?: string;
  event: string;
  data: unknown;
  retry?: number;
}

async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<SSEEvent> {
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        break;
      }
      buffer += decoder.decode(value, { stream: true });

      // ✅ 修复：兼容 \r\n\r\n 和 \n\n 两种分隔符
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || "";

      for (const raw of events) {
        if (!raw.trim()) continue;
        const event = parseEvent(raw);
        if (event) yield event;
      }
    }

    if (buffer.trim()) {
      const event = parseEvent(buffer);
      if (event) yield event;
    }
  } finally {
    reader.releaseLock();
  }
}

// ✅ 修复：行分割也兼容 \r\n 和 \n
function parseEvent(raw: string): SSEEvent | null {
  const lines = raw.split(/\r?\n/);
  let event = "message";
  let id: string | undefined;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line === "" || line.startsWith(":")) continue;

    const colonIdx = line.indexOf(":");
    if (colonIdx === -1) continue;

    const field = line.slice(0, colonIdx);
    const value = line.slice(colonIdx + 1).startsWith(" ")
      ? line.slice(colonIdx + 2)
      : line.slice(colonIdx + 1);

    switch (field) {
      case "event":
        event = value.replace(/\r$/, "");
        break; // 去掉尾部 \r
      case "data":
        dataLines.push(value.replace(/\r$/, ""));
        break;
      case "id":
        id = value.replace(/\r$/, "");
        break;
    }
  }

  if (dataLines.length === 0) return null;

  const dataStr = dataLines.join("\n");
  try {
    return { id, event, data: JSON.parse(dataStr) };
  } catch {
    return { id, event, data: dataStr };
  }
}

/** 标准 SSE fetch 客户端（POST + ReadableStream）。 */
export async function sendMessage(
  conversationId: string,
  body: Record<string, unknown>,
  handlers: StreamAssistantHandlers,
): Promise<string> {
  const abortController = new AbortController();
  const stop = () => {
    abortController.abort();
    handlers.onDone?.();
  };

  handlers.onControl?.(stop);

  // 120s 兜底超时
  const timeout = window.setTimeout(() => {
    abortController.abort();
    handlers.onDone?.();
  }, 120000);

  const response = await sse(
    `/conversations/${conversationId}/stream`,
    body,
    abortController,
  );

  if (!response.ok) {
    return `${response.status} ${response.statusText}`;
  }

  if (!response.body) {
    return `no body in response: ${response.status} ${response.statusText}`;
  }

  const reader = response.body.getReader();

  for await (const { event, data } of parseSSEStream(reader)) {
    console.log(event, data);

    switch (event) {
      // 运行时事件：Session 生命周期
      case "system.session_started":
      case "system.session_completed":
      case "system.session_error":
        window.clearTimeout(timeout);
        handlers.onDone?.(data as Record<string, unknown>);
        break;

      // 运行时事件：Round / Agent 生命周期
      case "system.round_started":
      case "system.agent_started":
        handlers.onMessageStart?.(data as Record<string, unknown>);
        break;
      case "system.agent_completed":
      case "system.agent_failed":
        handlers.onMessageEnd?.(data as Record<string, unknown>);
        break;

      // 运行时事件：工具调用
      case "agent.tool_calls_executed": {
        const payload = data as Record<string, unknown>;
        const toolEvents = payload.tool_events as Record<string, unknown>[];
        if (Array.isArray(toolEvents)) {
          for (const te of toolEvents) {
            const teRecord = te as Record<string, unknown>;
            const toolCallId = String(teRecord.call_id ?? "");
            const toolName = String(
              teRecord.tool_name ??
                (teRecord.function as Record<string, unknown>)?.name ??
                "",
            );
            if (toolCallId && toolName) {
              handlers.onToolCallStart?.({
                tool_call_id: toolCallId,
                tool_name: toolName,
              });
              handlers.onToolCallDone?.({
                tool_call_id: toolCallId,
                tool_name: toolName,
              });
            }
          }
        }
        break;
      }

      // 流式 token 和思考过程（增量追加）
      case "agent.thinking":
      case "agent.token": {
        const p = data as Record<string, unknown>;
        const agentId = String(p.agent_id || "");
        if (!agentId) break;
        if (event === "agent.token") {
          const token = String(p.token || "");
          if (token) handlers.onToken?.(agentId, token);
        } else {
          const thinking = String(p.thinking || p.task || "");
          if (thinking) handlers.onThinking?.(agentId, thinking);
        }
        break;
      }

      // 控制类 / 用户事件：前端暂不直接展示
      case "control.watchdog_triggered":
      case "control.scheduling_decision":
      case "control.escalation":
      case "user.waiting_for_input":
      case "user.input_received":
      case "user.input_queued":
        break;
    }
  }

  window.clearTimeout(timeout);
  handlers.onDone?.();

  return "ok";
}

export async function cancelAssistantReply(
  conversationId: string,
): Promise<{ cancelled: boolean }> {
  return await post<{ cancelled: boolean }>(
    `/conversations/${conversationId}/stream/cancel`,
    {},
  );
}
