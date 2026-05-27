import { StreamAssistantHandlers } from "@/types/messages";
import { get, post, sse } from "./client";
import type { ChatMessage, UploadedFile } from "@/types";

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
async function* parseSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
) {
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode(); // flush remaining bytes
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const chunk of events) {
      if (!chunk.trim()) continue;
      yield* parseEvent(chunk);
    }
  }

  if (buffer.trim()) {
    yield* parseEvent(buffer);
  }
}

function* parseEvent(chunk: string) {
  const lines = chunk.split("\n");
  let eventName = "message";
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith("event: ")) {
      eventName = line.slice(7).trim();
    } else if (line.startsWith("data: ")) {
      dataLines.push(line.slice(6).trim());
    }
  }

  if (dataLines.length === 0) return;

  const dataStr = dataLines.join("\n"); // ✅ 多行 data 用 \n 连接

  try {
    yield { event: eventName, data: JSON.parse(dataStr) };
  } catch {
    yield { event: eventName, data: dataStr };
  }
}

/** 标准 SSE fetch 客户端（POST + ReadableStream）。 */
export async function sendMessage(
  conversationId: string,
  content: string,
  handlers: StreamAssistantHandlers,
  quotedMessageId?: string,
  attachments: UploadedFile[] = [],
  thinkingEnabled?: boolean,
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

  const response = await sse<Response>(
    `/conversations/${conversationId}/stream`,
    {
      client_message_id: `client-${Date.now()}`,
      content_type: "text",
      content: {
        text: content,
        attachments: attachments.map((file) => ({
          file_id: file.file_id ?? file.id,
          filename: file.original_filename,
          content_type: file.content_type,
          size: file.size,
        })),
      },
      reply_to_message_id: quotedMessageId,
      thinking_enabled: thinkingEnabled,
    },
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
    switch (event) {
      case "message_start":
        handlers.onMessageStart?.(data as Record<string, unknown>);
        break;
      case "content_block_delta": {
        const payload = data as Record<string, unknown>;
        const deltaPayload = payload.delta;
        const deltaType =
          deltaPayload && typeof deltaPayload === "object"
            ? String((deltaPayload as { type?: unknown }).type ?? "text_delta")
            : "text_delta";
        const deltaText =
          deltaPayload &&
          typeof deltaPayload === "object" &&
          "text" in deltaPayload
            ? String((deltaPayload as { text?: unknown }).text ?? "")
            : "";
        if (deltaType === "reasoning_delta" && deltaText) {
          handlers.onReasoningDelta?.(deltaText, payload);
        } else if (deltaText) {
          handlers.onDelta?.(deltaText, payload);
        }
        break;
      }
      case "message:updated":
        handlers.onMessageUpdated?.(data as unknown as ChatMessage);
        break;
      case "message:new":
        handlers.onMessageNew?.(data as unknown as ChatMessage);
        break;
      case "tool_call_start":
        handlers.onToolCallStart?.(data as Record<string, unknown>);
        break;
      case "tool_call_done":
        handlers.onToolCallDone?.(data as Record<string, unknown>);
        break;
      case "message_stop":
        window.clearTimeout(timeout);
        handlers.onDone?.(data as Record<string, unknown>);
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
