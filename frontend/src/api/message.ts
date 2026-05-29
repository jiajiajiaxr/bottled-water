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
      // 业务层事件：用户消息已保存
      case "message:new":
        handlers.onMessageNew?.(data as unknown as ChatMessage);
        break;

      // 运行时事件：Session 生命周期
      case "system.session_started":
        handlers.onMessageStart?.(data as Record<string, unknown>);
        break;
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
        handlers.onMessageUpdated?.(data as unknown as ChatMessage);
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
              handlers.onToolCallStart?.({ tool_call_id: toolCallId, tool_name: toolName });
              handlers.onToolCallDone?.({ tool_call_id: toolCallId, tool_name: toolName });
            }
          }
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

/** 流式发送消息（统一走 sendMessage）。 */
export async function streamAssistantReply(
  conversationId: string,
  options: StreamAssistantHandlers,
): Promise<string> {
  return sendMessage(conversationId, "", options);
}
