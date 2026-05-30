import { useRef } from "react";
import { App as AntApp } from "antd";
import { api } from "@/api";
import {
  useConversationStore,
  useMessageStore,
  useArtifactStore,
} from "@/store";
import { useStreamingMessages } from "./useStreamingMessages";
import type { ChatMessage, UploadedFile, MessageAttachment } from "@/types";
import {
  makeMessage,
  stripInternalAgentOutput,
  isLikelyArtifactRequest,
  participantName,
} from "@/lib/message";

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
export function useMessageOperations(currentUserName: string) {
  const { message } = AntApp.useApp();
  const {
    conversations,
    activeId,
    activeConversation,
    updateConversations,
    updateActiveConversation,
  } = useConversationStore();
  const { historyMessages, setMessages, updateMessages } = useMessageStore();
  const { setArtifact } = useArtifactStore();
  const { updateLocalRunningConversationIds } = useConversationStore();

  // === 流式状态子模块 ===
  const streaming = useStreamingMessages();

  // SSE 停止回调引用
  const stopStreamRef = useRef<(() => void) | undefined>();

  const active = conversations.find((item) => item.id === activeId);

  // ============================================================
  // 流式传输核心
  // ============================================================

  /**
   * 建立 SSE 连接，接收 Agent 的流式回复。
   *
   * 流程：
   * 1. 根据对话参与者预创建占位消息（单 Agent 模式）
   * 2. 订阅 SSE 事件，实时更新流式消息池
   * 3. 传输结束后将流式消息归档到历史消息
   * 4. 拉取后端最新消息列表做兜底同步
   */
  const appendConversationStream = async (
    conversationId: string,
    body?: Record<string, unknown>,
  ) => {
    const agentParticipants =
      activeConversation?.participants.filter(
        (item) => item.participant_type === "agent" && item.agent_id,
      ) ?? [];
    const tempIdsByAgentId = new Map<string, string>();
    const tempIdsByAuthor = new Map<string, string>();

    /** 规范化后端推送的消息，补全缺失字段 */
    const normalizeIncomingMessage = (incoming: ChatMessage): ChatMessage => ({
      ...incoming,
      conversationId:
        incoming.conversationId ??
        (incoming as ChatMessage & { conversation_id?: string })
          .conversation_id ??
        conversationId,
      role: incoming.role ?? "assistant",
      kind: incoming.kind ?? "text",
      author:
        incoming.author ||
        (incoming as ChatMessage & { sender_name?: string }).sender_name ||
        "Agent",
      content:
        incoming.role === "assistant" && incoming.kind === "text"
          ? stripInternalAgentOutput(incoming.content)
          : incoming.content,
      createdAt:
        incoming.createdAt ??
        (incoming as ChatMessage & { created_at?: string }).created_at ??
        new Date().toISOString(),
      streamState:
        incoming.role === "assistant" && incoming.kind === "text"
          ? "done"
          : incoming.streamState,
    });

    /** 确保指定 messageId 的流式消息已存在于池中 */
    const ensureStreamingMessage = (
      messageId: string,
      author: string,
      agentId?: string,
    ) => {
      // 通过 ref 读取最新的 streamingMessages，避免闭包陈旧
      const currentStreaming = streaming.getStreamingMessages();
      if (currentStreaming.has(messageId)) return;

      const tempId =
        (agentId && tempIdsByAgentId.get(agentId)) ||
        tempIdsByAuthor.get(author);
      if (tempId && currentStreaming.has(tempId)) {
        const tempMsg = currentStreaming.get(tempId)!;
        if (agentId) tempIdsByAgentId.set(agentId, messageId);
        tempIdsByAuthor.set(author, messageId);

        streaming.removeStreamingMessage(tempId);
        streaming.startStreamingMessage({
          ...tempMsg,
          id: messageId,
          sender_id: agentId,
          author,
          rawContent: { ...(tempMsg.rawContent ?? {}), agent_id: agentId },
          streamState: "streaming",
        });
        return;
      }

      streaming.startStreamingMessage({
        id: messageId,
        conversationId,
        role: "assistant",
        kind: "text",
        author,
        content: "",
        rawContent: agentId ? { agent_id: agentId } : {},
        streamState: "streaming",
        createdAt: new Date().toISOString(),
        state: "active",
      });
    };

    /** 插入或更新最终消息（后端推送的完整消息） */
    const upsertFinalMessage = (incoming: ChatMessage) => {
      let normalized = normalizeIncomingMessage(incoming);
      const agentId =
        normalized.sender_id ||
        (normalized.rawContent?.agent_id as string | undefined);

      // 优先检查 streamingMessages：保留流式传输过程中已累积的内容
      const currentStreaming = streaming.getStreamingMessages();
      if (currentStreaming.has(normalized.id)) {
        const existing = currentStreaming.get(normalized.id)!;
        if (!normalized.content && existing.content) {
          normalized = { ...normalized, content: existing.content };
        }
        if (!normalized.thinking && existing.thinking) {
          normalized = { ...normalized, thinking: existing.thinking };
        }
        streaming.updateStreamingState(normalized.id, normalized);
        return;
      }

      // 检查 historyMessages（通过 getState 读取最新值，避免闭包陈旧）
      const latestHistory = useMessageStore.getState().historyMessages;
      const inHistory = latestHistory.some((item) => item.id === normalized.id);
      if (inHistory) {
        updateMessages((prev) =>
          prev.map((item) =>
            item.id === normalized.id ? { ...item, ...normalized } : item,
          ),
        );
        return;
      }

      // 检查是否有临时消息需要替换
      const tempId =
        (agentId && tempIdsByAgentId.get(agentId)) ||
        tempIdsByAuthor.get(normalized.author);
      if (tempId && streaming.getStreamingMessages().has(tempId)) {
        if (agentId) tempIdsByAgentId.set(agentId, normalized.id);
        tempIdsByAuthor.set(normalized.author, normalized.id);

        const tempMsg = streaming.streamingMessages.get(tempId)!;
        streaming.removeStreamingMessage(tempId);
        streaming.startStreamingMessage({
          ...normalized,
          content: normalized.content || tempMsg.content,
          thinking: normalized.thinking || tempMsg.thinking,
          streamState: "streaming",
        });
        return;
      }

      // 直接添加为历史消息
      updateMessages((prev) => [...prev, normalized]);
    };

    // 单 Agent 模式：预创建占位消息
    if (agentParticipants.length === 1) {
      const participant = agentParticipants[0];
      const author = participantName(participant);
      const agentId = participant.agent_id ?? participant.id ?? author;
      const placeholder = makeMessage({
        conversationId,
        role: "assistant",
        kind: "text",
        author,
        content: "",
        state: "active",
        rawContent: {
          agent_id: participant.agent_id,
          participant_id: participant.id,
        },
        streamState: "streaming",
      });
      tempIdsByAgentId.set(agentId, placeholder.id);
      tempIdsByAuthor.set(author, placeholder.id);
      streaming.startStreamingMessage(placeholder);
    }

    streaming.setStreamState("streaming");
    updateLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.add(conversationId);
      return next;
    });
    updateActiveConversation({
      ...activeConversation,
      updatedAt: new Date().toISOString(),
      unread: 0,
    });
    stopStreamRef.current = undefined;

    // 文本累积（来自 agent_completed 的 work_product）
    let rawBuffer = "";
    let completedPreview = "";
    const activeToolCalls = new Map<
      string,
      { toolName: string; toolCallId: string }
    >();
    let currentMessageId = "";

    const updateActiveToolCalls = (messageId: string) => {
      if (!messageId) return;
      const msg = streaming.getStreamingMessages().get(messageId);
      if (!msg) return;
      streaming.updateStreamingState(messageId, {
        rawContent: {
          ...msg.rawContent,
          _activeToolCalls: Array.from(activeToolCalls.values()),
        },
      });
    };

    try {
      await api.sendMessage(
        conversationId,
        (body.content as { text?: string }).text || "",
        {
          onMessageStart: (payload) => {
            // system.session_started / system.round_started / system.agent_started
            const agentId = String(payload.agent_id || "");
            const author = String(payload.agent_name || "Agent");
            currentMessageId = agentId || `stream-${Date.now()}`;
            ensureStreamingMessage(currentMessageId, author, agentId);
            activeToolCalls.clear();
          },
          onMessageUpdated: (payload) => {
            // system.agent_completed / system.agent_failed：提取 work_product
            const p = payload as unknown as Record<string, unknown>;
            const workProduct = String(p.work_product ?? "");
            const agentId = String(p.agent_id || "");
            if (workProduct && currentMessageId) {
              streaming.updateStreamingContent(currentMessageId, workProduct);
            }
            rawBuffer += workProduct;
            upsertFinalMessage({
              id: currentMessageId || "",
              conversationId,
              role: "assistant",
              kind: "text",
              author: String(p.agent_name || "Agent"),
              content: workProduct,
              state: "active",
              rawContent: { agent_id: agentId },
              createdAt: new Date().toISOString(),
              streamState: "done",
            });
          },
          onMessageNew: (incoming) => {
            if (incoming.kind === "preview_card") upsertFinalMessage(incoming);
          },
          onToolCallStart: (payload) => {
            const toolName = String(payload.tool_name || "");
            const toolCallId = String(payload.tool_call_id || "");
            if (toolName && toolCallId) {
              activeToolCalls.set(toolCallId, { toolName, toolCallId });
              updateActiveToolCalls(currentMessageId);
            }
          },
          onToolCallDone: (payload) => {
            const toolCallId = String(payload.tool_call_id || "");
            if (toolCallId) {
              activeToolCalls.delete(toolCallId);
              updateActiveToolCalls(currentMessageId);
            }
          },
          onDone: () => {
            activeToolCalls.clear();
            streaming.finishAllStreamingMessages((msg) => ({
              content:
                msg.role === "assistant" && msg.kind === "text"
                  ? stripInternalAgentOutput(msg.content)
                  : msg.content,
              rawContent: {
                ...msg.rawContent,
                _activeToolCalls: [],
              },
            }));
          },
          onControl: (stop) => {
            stopStreamRef.current = stop;
          },
        },
        (body as { reply_to_message_id?: string })?.reply_to_message_id,
        (body as { content?: { attachments: UploadedFile[] } })?.content?.attachments ?? [],
        (body as { thinking_enabled?: boolean })?.thinking_enabled,
        (body as { model_config_id?: string })?.model_config_id,
      );
      streaming.setStreamState("done");

      // 兜底：拉取后端最新状态做同步
      const [freshMessages, freshArtifact] = await Promise.all([
        api.messages(conversationId),
        api.artifact(conversationId),
      ]).catch(() => [undefined, undefined]);

      if (freshMessages) {
        const cleanMessages = freshMessages.map((item) =>
          item.role === "assistant" && item.kind === "text"
            ? {
                ...item,
                content: stripInternalAgentOutput(item.content),
                streamState: "done" as const,
              }
            : item,
        );
        const hasPreviewCard = cleanMessages.some(
          (item) => item.kind === "preview_card",
        );
        setMessages(
          hasPreviewCard || !freshArtifact
            ? cleanMessages
            : [
                ...cleanMessages,
                makeMessage({
                  conversationId,
                  role: "assistant",
                  kind: "preview_card",
                  author: "Artifact Agent",
                  content: `预览产物：${freshArtifact.title}`,
                  streamState: "done",
                  state: "inactive",
                }),
              ],
        );
        const lastAssistant = [...cleanMessages]
          .reverse()
          .find((item) => item.role === "assistant" && item.kind === "text");

        completedPreview = (
          lastAssistant?.content ||
          stripInternalAgentOutput(rawBuffer) ||
          "done"
        ).slice(0, 120);

        updateActiveConversation({
          ...activeConversation,
          lastMessage: completedPreview,
          updatedAt: new Date().toISOString(),
        });
      }

      if (freshArtifact) setArtifact(freshArtifact);
    } catch (error) {
      activeToolCalls.clear();
      const fallbackPreview =
        stripInternalAgentOutput(rawBuffer).slice(0, 120) || "reply failed";
      completedPreview = fallbackPreview;
      streaming.setStreamState("error");

      for (const [msgId, msg] of streaming.streamingMessages) {
        streaming.finishStreamingMessage(msgId, {
          streamState: "error",
          content: msg.content || fallbackPreview,
          rawContent: { ...msg.rawContent, _activeToolCalls: [] },
        });
      }

      throw error;
    } finally {
      updateLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      if (completedPreview) {
        updateActiveConversation({
          ...activeConversation,
          lastMessage: completedPreview,
          updatedAt: new Date().toISOString(),
        });
      }
    }
  };

  // ============================================================
  // 停止流式
  // ============================================================

  const stopStreaming = async () => {
    if (!activeId) return;
    stopStreamRef.current?.();
    stopStreamRef.current = undefined;
    streaming.setStreamState("done");
    updateLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.delete(activeId);
      return next;
    });
    updateConversations((current) =>
      current.map((item) =>
        item.id === activeId
          ? {
              ...item,
              lastMessage: "已停止本次响应。",
              updatedAt: new Date().toISOString(),
            }
          : item,
      ),
    );

    for (const [msgId, msg] of streaming.streamingMessages) {
      streaming.updateStreamingState(msgId, {
        streamState: "done",
        content: msg.content || "已停止接收本次回复。",
      });
      streaming.finishStreamingMessage(msgId);
    }

    await api.cancelAssistantReply(activeId).catch(() => undefined);
    message.info("已停止本次响应");
  };

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
    const localMessage = makeMessage({
      conversationId,
      role: "user",
      kind: "text",
      author: currentUserName,
      content,
      state: "active",
      rawContent: { text: content, attachments: localAttachments },
      attachments: localAttachments,
      quotedMessageId: quoted?.id,
    });

    // 1. 本地追加用户消息
    updateMessages((prev) => [...prev, localMessage]);
    updateConversations((current) =>
      current.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              lastMessage: content,
              updatedAt: new Date().toISOString(),
              unread: 0,
            }
          : item,
      ),
    );

    // 2. 标准模式：POST 发送消息并接收流式响应
    const body = {
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
    };

    try {
      await appendConversationStream(conversationId, body);

      // 3. 流式结束后检查产物
      if (isLikelyArtifactRequest(content)) {
        const freshArtifact = await api
          .artifact(conversationId)
          .catch(() => undefined);
        if (freshArtifact) {
          setArtifact(freshArtifact);
          const exists = historyMessages.some(
            (item) =>
              item.kind === "preview_card" &&
              item.rawContent?.artifact_id === freshArtifact.id,
          );
          if (!exists) {
            updateMessages((prev) => [
              ...prev,
              makeMessage({
                conversationId,
                role: "assistant",
                kind: "preview_card",
                author: "Artifact Agent",
                content: `预览产物：${freshArtifact.title}`,
                state: "inactive",
                rawContent: { artifact_id: freshArtifact.id },
                streamState: "done",
              }),
            ]);
          }
          updateConversations((current) =>
            current.map((item) =>
              item.id === conversationId
                ? {
                    ...item,
                    lastMessage:
                      "已生成产物卡片，可点击后在右侧预览、编辑和部署。",
                    updatedAt: new Date().toISOString(),
                  }
                : item,
            ),
          );
        }
      }
    } catch (error) {
      const index = historyMessages.findIndex(
        (item) => item.id === localMessage.id,
      );
      if (index !== -1) {
        updateMessages((prev) =>
          prev.map((item, i) =>
            i === index
              ? {
                  ...item,
                  kind: "error",
                  content: `${content}\n\n发送失败：${error instanceof Error ? error.message : "网络异常"}`,
                }
              : item,
          ),
        );
      }
      message.error("消息发送失败");
    }
  };

  // ============================================================
  // 重新生成
  // ============================================================

  const regenerate = (source: ChatMessage) => {
    if (!activeId) return;
    const body = {
      content_type: "text",
      content: { text: `请重新生成这条回复：${source.content}` },
      regenerate_message_id: source.id,
    };
    appendConversationStream(activeId, body).catch(() =>
      streaming.setStreamState("error"),
    );
  };

  return {
    send,
    regenerate,
    stopStreaming,
    streamingMessages: streaming.streamingMessages,
    streamState: streaming.streamState,
    getMessageVersion: useMessageStore.getState().getMessageVersion,
  };
}
