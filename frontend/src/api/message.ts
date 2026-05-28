import {
  eventPayload,
  request,
  type StreamAssistantHandlers,
  wait,
} from "./client";
import { demoMessages, demoUser } from "../mock";
import { isVisibleChatMessage } from "../lib/message";
import type { ChatMessage, UploadedFile } from "../types";

export async function messages(conversationId: string): Promise<ChatMessage[]> {
  try {
    const result = await request<{ items: ChatMessage[] } | ChatMessage[]>(
      `/conversations/${conversationId}/messages`,
    );
    const items = Array.isArray(result) ? result : result.items;
    return items.filter(isVisibleChatMessage);
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
      let settled = false;
      const source = new EventSource(
        `${"/api/v1"}/conversations/${conversationId}/stream?replay=false${token ? `&token=${encodeURIComponent(token)}` : ""}`,
      );
      let timeout = 0;
      const close = (payload?: Record<string, unknown>, fallback = "任务已完成。") => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        source.close();
        handlers.onDone?.(payload);
        resolve(buffer || fallback);
      };
      const stop = () => close(undefined, buffer);
      handlers.onControl?.(stop);
      timeout = window.setTimeout(() => {
        close(undefined, "任务正在后台执行，稍后刷新可查看完整结果。");
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
        handlers.onMessageNew?.(
          eventPayload(event) as unknown as ChatMessage,
        );
      });
      source.addEventListener("tool_call_start", (event) => {
        handlers.onToolCallStart?.(eventPayload(event));
      });
      source.addEventListener("tool_call_done", (event) => {
        handlers.onToolCallDone?.(eventPayload(event));
      });
      source.addEventListener("message_stop", (event) => {
        const payload = eventPayload(event);
        const stopReason = String(payload.stop_reason || "");
        if (
          ["workflow_completed", "generation_finished", "cancelled"].includes(
            stopReason,
          )
        ) {
          close(payload);
        }
      });
      source.addEventListener("workflow:completed", () => {
        // 工作流完成事件可能早于 Task 状态落库，等待 generation_finished 统一收尾。
      });
      source.addEventListener("workflow:failed", () => {
        // 失败路径后端也会发送 generation_finished，避免提前刷新到旧任务状态。
      });
      source.addEventListener("workflow:cancelled", () => {
        // 取消同样等待全局结束事件，保持单一收尾语义。
      });
      source.addEventListener("generation_finished", (event) => {
        close(eventPayload(event));
      });
      source.addEventListener("generation:cancelled", (event) => {
        close(eventPayload(event), "本次响应已停止。");
      });
      source.addEventListener("error", () => {
        if (settled) return;
        window.clearTimeout(timeout);
        source.close();
        if (buffer) {
          handlers.onDone?.();
          resolve(buffer);
        } else {
          reject(new Error("stream failed"));
        }
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
  }).then((result) => result || text || `收到：${prompt}`);
}

export async function cancelAssistantReply(
  conversationId: string,
): Promise<{ cancelled: boolean }> {
  return await request<{ cancelled: boolean }>(
    `/conversations/${conversationId}/stream/cancel`,
    { method: "POST" },
  );
}
