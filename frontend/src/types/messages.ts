import { ChatMessage } from "./chat";

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
  onToken?: (agentId: string, token: string) => void;
  onThinking?: (agentId: string, thinking: string) => void;
};

export type MessageBody = {
  replay: boolean;
  content_type: string;
  content: {
    text: string;
    attachments: string[];
  };
  reply_to_message_id: string;
  thinking_enabled: boolean;
  regenerate_message_id: string;
};
