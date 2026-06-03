import { useEffect } from "react";
import { App as AntApp } from "antd";
import { api } from "@/api";
import { disconnectConversationWS } from "@/api/websocket";
import {
  useConversationStore,
  useMessageStore,
  useArtifactStore,
  useUIStore,
} from "@/store";
import { useStreamingMessages } from "./useStreamingMessages";
import { makeMessage } from "@/lib";
import type { ChatMessage, UploadedFile, MessageAttachment } from "@/types";
import type { MessageBody } from "@/types/messages";

/**
 * 消息操作 Hook。
 *
 * 职责：封装消息发送的完整业务流，包括：
 * - 用户消息的发送与本地占位
 * - SSE 流式响应的接收与状态更新
 * - 流式结束后的归档与对话元数据同步
 * - 停止流式、重新生成等控制操作
 *
 * 流式消息的状态管理委托给 {@link useStreamingMessages}，
 * 本 Hook 只负责业务编排（何时调用、以什么顺序调用）。
 */
export function useMessageOperations(userName?: string) {
  const { message } = AntApp.useApp();
  const { activeId } = useConversationStore();
  const { updateMessages } = useMessageStore();
  // === 流式状态子模块 ===
  const streaming = useStreamingMessages(activeId);

  // 切换会话时清理旧连接的 WebSocket
  useEffect(() => {
    return () => {
      if (activeId) {
        disconnectConversationWS(activeId);
      }
    };
  }, [activeId]);

  // ============================================================
  // 发送消息
  // ============================================================

  const send = async (
    content: string,
    quoted?: ChatMessage,
    attachments: UploadedFile[] = [],
    thinkingEnabled?: boolean,
    modelConfigId?: string,
  ) => {
    if (!activeId) return;

    const conversationId = activeId;
    const scheduleMode = useUIStore.getState().scheduleMode;
    const localAttachments: MessageAttachment[] = attachments.map((file) => ({
      file_id: file.file_id ?? file.id,
      id: file.id,
      filename: file.filename,
      original_filename: file.original_filename,
      content_type: file.content_type,
      size: file.size,
      parse_status: file.parse_status,
      public_url: file.public_url,
    }));

    // 2. 乐观添加用户消息到历史记录，确保发送后立即展示
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

    // 3. 通过 WebSocket 发送消息并接收流式响应
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
      scheduling_strategy: scheduleMode === "workflow" ? "workflow" : "tech_lead",
    };

    try {
      await api.sendMessageWs(conversationId, body, streaming.streamHandlers);
    } catch (error) {
      // 处理错误
    } finally {
      // 清理状态
    }
  };

  return {
    send,
    streamingMessages: streaming.streamingMessages,
    displayOrder: streaming.displayOrder,
  };
}
