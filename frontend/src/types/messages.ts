import { ChatMessage } from "./chat";

export type StreamAssistantHandlers = {
  onDelta?: (delta: string, payload: Record<string, unknown>) => void;
  onReasoningDelta?: (delta: string, payload: Record<string, unknown>) => void;
  onMessageStart?: (payload: Record<string, unknown>) => void;
  onMessageEnd?: (message: Record<string, unknown>) => void;
  onMessageStop?: (message: Record<string, unknown>) => void;
  onMessageNew?: (message: ChatMessage) => void;
  onMessageUpdated?: (message: ChatMessage) => void;
  onToolCallStart?: (payload: Record<string, unknown>) => void;
  onToolCallDone?: (payload: Record<string, unknown>) => void;
  onTaskStatusChanged?: (payload: Record<string, unknown>) => void;
  onDone?: (payload?: Record<string, unknown>) => void;
  onControl?: (stop: () => void) => void;
  onToken?: (
    agentId: string,
    token: string,
    payload?: Record<string, unknown>,
  ) => void;
  onThinking?: (
    agentId: string,
    thinking: string,
    payload?: Record<string, unknown>,
  ) => void;
  onRuntimeEvent?: (event: string, payload: Record<string, unknown>) => void;
};

/** 消息内容中附件的精简结构（发送时只需要这几个字段） */
export type MessageBodyAttachment = {
  file_id?: string;
  id?: string;
  filename?: string;
  content_type?: string;
  size?: number;
};

/** 消息内容结构 */
export type MessageBodyContent = {
  text?: string;
  attachments?: MessageBodyAttachment[];
};

/** 发送消息请求体（与后端 SendMessagePayload 对齐） */
export type MessageBody = {
  client_message_id?: string;
  content_type?: string;
  content?: MessageBodyContent;
  text?: string;
  prompt?: string;
  attachments?: MessageBodyAttachment[];
  reply_to_message_id?: string;
  quotedMessageId?: string;
  thinking_enabled?: boolean;
  scheduling_strategy?: "workflow" | "tech_lead" | "single_agent";
  regenerate_message_id?: string;
  model_config_id?: string;
};
