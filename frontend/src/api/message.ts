import {
  request,
  wait,
  eventPayload,
  type StreamAssistantHandlers,
} from "./client";
import { demoUser, demoMessages } from "@/mock";
import type { ChatMessage, UploadedFile } from "@/types";

export async function messages(conversationId: string): Promise<ChatMessage[]> {
  try {
    const result = await request<{ items: ChatMessage[] } | ChatMessage[]>(
      `/conversations/${conversationId}/messages`,
    );
    return Array.isArray(result) ? result : result.items;
  } catch {
    return demoMessages[conversationId] ?? [];
  }
}

export async function sendMessage(
  conversationId: string,
  content: string,
  quotedMessageId?: string,
  attachments: UploadedFile[] = [],
  thinkingEnabled?: boolean,
): Promise<ChatMessage> {
  try {
    return await request<ChatMessage>(
      `/conversations/${conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
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
        }),
      },
    );
  } catch {
    const normalizedAttachments = attachments.map((file) => ({
      file_id: file.file_id ?? file.id,
      filename: file.original_filename,
      original_filename: file.original_filename,
      content_type: file.content_type,
      size: file.size,
      parse_status: file.parse_status,
      public_url: file.public_url,
    }));
    return {
      id: `msg-${Date.now()}`,
      conversationId,
      role: "user",
      kind: "text",
      author: demoUser.name,
      content,
      rawContent: { text: content, attachments: normalizedAttachments },
      attachments: normalizedAttachments,
      quotedMessageId,
      createdAt: new Date().toISOString(),
    };
  }
}

export async function streamAssistantReply(
  conversationId: string,
  handlersOrDelta: StreamAssistantHandlers | ((delta: string) => void),
  onDone?: () => void,
  onControl?: (stop: () => void) => void,
): Promise<string> {
  const handlers: StreamAssistantHandlers =
    typeof handlersOrDelta === "function"
      ? { onDelta: (delta) => handlersOrDelta(delta), onDone, onControl }
      : handlersOrDelta;
  try {
    const token = window.localStorage.getItem("agenthub_token");
    return await new Promise<string>((resolve, reject) => {
      let buffer = "";
      const source = new EventSource(
        `${"/api/v1"}/conversations/${conversationId}/stream?replay=false${token ? `&token=${encodeURIComponent(token)}` : ""}`,
      );
      let timeout = 0;
      const stop = () => {
        window.clearTimeout(timeout);
        source.close();
        handlers.onDone?.();
        resolve(buffer);
      };
      handlers.onControl?.(stop);
      timeout = window.setTimeout(() => {
        source.close();
        handlers.onDone?.();
        resolve(buffer || "任务正在后台执行，稍后刷新可查看完整结果。");
      }, 120000);
      source.addEventListener("message_start", (event) => {
        handlers.onMessageStart?.(eventPayload(event));
      });
      source.addEventListener("content_block_delta", (event) => {
        const payload = eventPayload(event);
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
          console.log(
            "[SSE reasoning_delta] text=",
            deltaText.slice(0, 50),
            "payload=",
            payload,
          );
          handlers.onReasoningDelta?.(deltaText, payload);
        } else if (deltaText) {
          buffer += deltaText;
          handlers.onDelta?.(deltaText, payload);
        }
      });
      source.addEventListener("message:updated", (event) => {
        handlers.onMessageUpdated?.(
          eventPayload(event) as unknown as ChatMessage,
        );
      });
      source.addEventListener("message:new", (event) => {
        handlers.onMessageNew?.(eventPayload(event) as unknown as ChatMessage);
      });
      source.addEventListener("tool_call_start", (event) => {
        handlers.onToolCallStart?.(eventPayload(event));
      });
      source.addEventListener("tool_call_done", (event) => {
        handlers.onToolCallDone?.(eventPayload(event));
      });
      source.addEventListener("message_stop", (event) => {
        window.clearTimeout(timeout);
        source.close();
        handlers.onDone?.(eventPayload(event));
        resolve(buffer || "主控 Agent 已完成任务编排。");
      });
      source.addEventListener("error", () => {
        window.clearTimeout(timeout);
        source.close();
        if (buffer) {
          handlers.onDone?.();
          resolve(buffer);
        } else reject(new Error("stream failed"));
      });
    });
  } catch {
    await wait(350);
    const fallback =
      "模型流式连接暂不可用，任务已进入后台处理，可稍后刷新查看完整结果。";
    handlers.onDelta?.(fallback, {});
    handlers.onDone?.();
    return fallback;
  }
}

export async function assistantReply(
  conversationId: string,
  prompt: string,
): Promise<string> {
  let text = "";
  return await streamAssistantReply(conversationId, (delta) => {
    text += delta;
  }).then((result) => result || text || `收到："${prompt}"。`);
}

export async function cancelAssistantReply(
  conversationId: string,
): Promise<{ cancelled: boolean }> {
  return await request<{ cancelled: boolean }>(
    `/conversations/${conversationId}/stream/cancel`,
    { method: "POST" },
  );
}
