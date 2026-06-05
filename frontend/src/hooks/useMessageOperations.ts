import { useEffect } from "react";
import { api } from "@/api";
import { disconnectConversationWS } from "@/api/websocket";
import {
  useConversationStore,
  useMessageStore,
} from "@/store";
import { makeMessage } from "@/lib";
import { applyRuntimeEvent } from "@/lib/runtimeEvents";
import { useStreamingMessages } from "./useStreamingMessages";
import type { ChatMessage, UploadedFile, MessageAttachment } from "@/types";
import type { MessageBody, StreamAssistantHandlers } from "@/types/messages";

/**
 * 封装聊天消息发送与流式响应状态同步。
 */
export function useMessageOperations(userName?: string) {
  const { activeId } = useConversationStore();
  const { updateMessages } = useMessageStore();
  const streaming = useStreamingMessages(activeId);

  useEffect(() => {
    return () => {
      if (activeId) {
        disconnectConversationWS(activeId);
      }
    };
  }, [activeId]);

  const send = async (
    content: string,
    quoted?: ChatMessage,
    attachments: UploadedFile[] = [],
    thinkingEnabled?: boolean,
    modelConfigId?: string,
  ) => {
    if (!activeId) return;

    const conversationId = activeId;
    const activeConversation = useConversationStore
      .getState()
      .conversations.find((item) => item.id === conversationId);
    const workflowEnabled = Boolean(activeConversation?.workflow_enabled);
    const schedulingStrategy =
      activeConversation?.chat_type === "single"
        ? "single_agent"
        : workflowEnabled
          ? "workflow"
          : "tech_lead";
    const localAttachments = normalizeAttachments(attachments);

    const userMessage = makeMessage({
      conversationId,
      role: "user",
      kind: "text",
      author: userName || "我",
      content,
      streamState: "done",
      state: "active",
      attachments: localAttachments,
      quotedMessageId: quoted?.id,
    });
    updateMessages((prev) => [...prev, userMessage]);

    const body: MessageBody = {
      content_type: "text",
      content: {
        text: content,
        attachments: localAttachments.map((file) => ({
          file_id: file.file_id ?? file.id,
          filename: file.filename,
          content_type: file.content_type,
          size: file.size,
        })),
      },
      reply_to_message_id: quoted?.id,
      thinking_enabled: thinkingEnabled,
      model_config_id: modelConfigId,
      client_message_id: `client-${Date.now()}`,
      scheduling_strategy: schedulingStrategy,
    };

    markConversationRunning(conversationId);

    try {
      await api.sendMessageWs(
        conversationId,
        body,
        createStreamHandlers(conversationId, streaming.streamHandlers),
      );
    } catch {
      clearConversationRunning(conversationId);
    }
  };

  return {
    send,
    streamingMessages: streaming.streamingMessages,
    displayOrder: streaming.displayOrder,
  };
}

function normalizeAttachments(files: UploadedFile[]): MessageAttachment[] {
  return files.map((file) => ({
    file_id: file.file_id ?? file.id,
    id: file.id,
    filename: file.filename,
    original_filename: file.original_filename,
    content_type: file.content_type,
    size: file.size,
    parse_status: file.parse_status,
    public_url: file.public_url,
  }));
}

function createStreamHandlers(
  conversationId: string,
  baseHandlers: StreamAssistantHandlers,
): StreamAssistantHandlers {
  return {
    ...baseHandlers,
    onRuntimeEvent: (event, payload) => {
      baseHandlers.onRuntimeEvent?.(event, payload);
      const store = useConversationStore.getState();
      const current = store.conversations.find((item) => item.id === conversationId);
      if (current) {
        store.updateConversation(
          conversationId,
          applyRuntimeEvent(current, event, payload),
        );
      }
      if (isTerminalRuntimeEvent(event)) {
        clearConversationRunning(conversationId);
      }
    },
    onDone: (payload) => {
      baseHandlers.onDone?.(payload);
      clearConversationRunning(conversationId);
    },
  };
}

function markConversationRunning(conversationId: string) {
  const store = useConversationStore.getState();
  store.updateConversation(conversationId, { generation_status: "running" });
  store.updateLocalRunningConversationIds((current) => {
    const next = new Set(current);
    next.add(conversationId);
    return next;
  });
}

function clearConversationRunning(conversationId: string) {
  const store = useConversationStore.getState();
  store.updateConversation(conversationId, { generation_status: "idle" });
  store.updateLocalRunningConversationIds((current) => {
    const next = new Set(current);
    next.delete(conversationId);
    return next;
  });
}

function isTerminalRuntimeEvent(event: string) {
  return [
    "system.session_completed",
    "system.session_cancelled",
    "system.session_error",
    "generation_finished",
    "generation:finished",
    "generation:cancelled",
    "generation:failed",
    "workflow_completed",
    "workflow:completed",
    "workflow:run_completed",
    "workflow_cancelled",
    "workflow:cancelled",
    "workflow_failed",
    "workflow:failed",
    "cancelled",
    "failed",
    "control.cancel",
  ].includes(event);
}
