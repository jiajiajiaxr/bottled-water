import type { StreamAssistantHandlers, MessageBody } from "@/types/messages";
import type { ChatMessage } from "@/types";
import { API_BASE, get, post, sse } from "./client";
import { getConversationWS } from "./websocket";

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

/**
 * 分发流式事件到对应的 handlers。
 * SSE 与 WebSocket 共用的事件处理逻辑。
 */
function dispatchStreamEvent(
  event: string,
  data: unknown,
  handlers: StreamAssistantHandlers,
): void {
  switch (event) {
    case "message_start":
      handlers.onMessageStart?.(data as Record<string, unknown>);
      break;
    case "content_block_delta": {
      const payload = data as Record<string, unknown>;
      const delta = payload.delta as Record<string, unknown> | undefined;
      const text = String(delta?.text || "");
      if (!text) break;
      if (delta?.type === "reasoning_delta") {
        handlers.onReasoningDelta?.(text, payload);
      } else {
        handlers.onDelta?.(text, payload);
      }
      break;
    }
    case "message_stop":
      handlers.onMessageEnd?.(data as Record<string, unknown>);
      handlers.onMessageStop?.(data as Record<string, unknown>);
      break;
    case "task:status_changed":
      handlers.onTaskStatusChanged?.(data as Record<string, unknown>);
      break;
    case "message:new":
      handlers.onMessageNew?.(data as ChatMessage);
      break;
    case "generation_finished":
    case "generation:cancelled":
    case "cancelled":
    case "failed":
      handlers.onDone?.(data as Record<string, unknown>);
      break;

    // 运行时事件：Session 生命周期
    case "system.session_started":
    case "system.session_completed":
    case "system.session_cancelled":
      handlers.onRuntimeEvent?.(event, data as Record<string, unknown>);
      break;
    case "system.session_error":
      handlers.onDone?.(data as Record<string, unknown>);
      break;

    // 运行时事件：Round / Agent 生命周期
    case "system.round_started":
      break;
    case "system.agent_started":
      handlers.onMessageStart?.(data as Record<string, unknown>);
      break;
    case "system.agent_completed":
    case "system.agent_failed":
      handlers.onMessageEnd?.(data as Record<string, unknown>);
      break;

    case "scheduler.decision":
    case "agent.state_changed":
    case "agent.report":
    case "agent.failed":
    case "control.cancel":
      handlers.onRuntimeEvent?.(event, data as Record<string, unknown>);
      break;
    case "agent.tool_result": {
      const payload = data as Record<string, unknown>;
      handlers.onRuntimeEvent?.(event, payload);
      const toolName = String(payload.tool || payload.tool_name || "");
      handlers.onToolCallDone?.({
        tool_name: toolName,
        status: payload.success === false ? "failed" : "succeeded",
        result: payload.result,
        error: payload.error,
      });
      const previewMessage = previewCardFromToolResult(payload);
      if (previewMessage) handlers.onMessageNew?.(previewMessage);
      break;
    }

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
    case "agent.thinking": {
      const pt = data as Record<string, unknown>;
      const agentId = String(pt.agent_id || "");
      const thinking = String(pt.thinking || "");
      if (agentId && thinking) handlers.onThinking?.(agentId, thinking);
      break;
    }
    case "agent.token": {
      const p = data as Record<string, unknown>;
      const agentId = String(p.agent_id || "");

      if (!agentId) break;
      const token = String(p.token || "");
      if (token) handlers.onToken?.(agentId, token);
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

/** 标准 SSE fetch 客户端（POST + ReadableStream）。 */
function previewCardFromToolResult(
  payload: Record<string, unknown>,
): ChatMessage | undefined {
  const result = asRecord(payload.result) || {};
  const output = asRecord(result.output) || asRecord(result.result) || result;
  const artifact = asRecord(output.artifact) || {};
  const artifactId = stringValue(output.artifact_id ?? artifact.id);
  if (!artifactId) return undefined;
  const conversationId = stringValue(
    artifact.conversationId ?? artifact.conversation_id ?? output.conversation_id,
  );
  if (!conversationId) return undefined;
  const title =
    stringValue(artifact.title ?? artifact.name ?? output.title ?? output.filename) ||
    "AgentHub 产物";
  const messageId = stringValue(output.preview_message_id) || `preview-${artifactId}`;
  return {
    id: messageId,
    conversationId,
    role: "assistant",
    kind: "preview_card",
    author: "Master Agent",
    content: `预览产物：${title}`,
    rawContent: {
      artifact_id: artifactId,
      title,
      artifact_type: output.artifact_type ?? artifact.type,
      preview_url: output.preview_url ?? artifact.previewUrl,
      export_url: output.export_url ?? artifact.exportUrl,
      format: output.format ?? artifact.format,
      media_type: output.media_type ?? artifact.media_type,
      filename: output.filename ?? artifact.filename,
    },
    createdAt: new Date().toISOString(),
    streamState: "done",
    state: "active",
    status: "completed",
  };
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : undefined;
}

function stringValue(value: unknown): string {
  return typeof value === "string" && value ? value : "";
}

export async function sendMessage(
  conversationId: string,
  body: MessageBody,
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
    if (event === "system.session_error") {
      window.clearTimeout(timeout);
    }
    dispatchStreamEvent(event, data, handlers);
  }

  window.clearTimeout(timeout);
  handlers.onDone?.();

  return "ok";
}

export function streamAssistantReply(
  conversationId: string,
  handlers: StreamAssistantHandlers,
): Promise<string> {
  let accumulated = "";
  let settled = false;
  const source = new EventSource(
    `${API_BASE}/conversations/${conversationId}/stream`,
  );
  const finish = (payload?: Record<string, unknown>) => {
    if (settled) return;
    settled = true;
    source.close();
    handlers.onDone?.(payload);
  };

  return new Promise((resolve) => {
    const complete = (payload?: Record<string, unknown>) => {
      finish(payload);
      resolve(accumulated || "ok");
    };
    const handle = (eventName: string) => (event: MessageEvent) => {
      const data = event.data ? JSON.parse(event.data) : {};
      if (eventName === "content_block_delta") {
        const payload = data as Record<string, unknown>;
        const delta = payload.delta as Record<string, unknown> | undefined;
        const text = String(delta?.text || "");
        accumulated += text;
      }
      if (
        eventName === "generation_finished" ||
        eventName === "generation:cancelled" ||
        eventName === "cancelled" ||
        eventName === "failed" ||
        eventName === "system.session_error"
      ) {
        complete(data as Record<string, unknown>);
        return;
      }
      dispatchStreamEvent(eventName, data, handlers);
    };

    [
      "message_start",
      "content_block_delta",
      "message_stop",
      "task:status_changed",
      "workflow:completed",
      "generation_finished",
      "generation:cancelled",
      "cancelled",
      "failed",
      "system.session_error",
    ].forEach((eventName) => source.addEventListener(eventName, handle(eventName)));
    source.onerror = () => complete({ reason: "event_source_error" });
  });
}

export async function cancelAssistantReply(
  conversationId: string,
): Promise<{ cancelled: boolean }> {
  return await post<{ cancelled: boolean }>(
    `/conversations/${conversationId}/stream/cancel`,
    {},
  );
}

/**
 * WebSocket 版本的消息发送。
 *
 * 保持与 sendMessage 相同的接口，内部通过 WebSocket 长连接传输。
 */
export async function sendMessageWs(
  conversationId: string,
  body: MessageBody,
  handlers: StreamAssistantHandlers,
): Promise<string> {
  const ws = getConversationWS(conversationId);
  if (ws.readyState !== WebSocket.OPEN) {
    await ws.connect();
  }

  const requestId = `req-${Date.now()}`;
  let resolved = false;

  return new Promise((resolve) => {
    const stop = () => {
      ws.send("chat.cancel", {}, requestId);
      handlers.onDone?.();
    };
    handlers.onControl?.(stop);

    const timeout = window.setTimeout(() => {
      if (!resolved) {
        resolved = true;
        handlers.onDone?.();
        resolve("timeout");
      }
    }, 120000);

    const unsubscribe = ws.onMessage((event, data) => {
      switch (event) {
        case "system.session_completed":
        case "generation_finished":
        case "generation:cancelled":
          window.clearTimeout(timeout);
          if (!resolved) {
            resolved = true;
            unsubscribe();
            dispatchStreamEvent(event, data, handlers);
            if (event === "system.session_completed") {
              handlers.onDone?.();
            }
            resolve("ok");
          }
          break;
        case "system.session_error":
          window.clearTimeout(timeout);
          if (!resolved) {
            resolved = true;
            unsubscribe();
            dispatchStreamEvent(event, data, handlers);
            resolve("error");
          }
          break;
        default:
          dispatchStreamEvent(event, data, handlers);
          break;
      }
    });

    ws.send("chat.send", body, requestId);
  });
}

/**
 * WebSocket 版本的取消助手回复。
 */
export function cancelAssistantReplyWs(conversationId: string): void {
  const ws = getConversationWS(conversationId);
  if (ws.readyState === WebSocket.OPEN) {
    ws.send("chat.cancel", {});
  }
}
