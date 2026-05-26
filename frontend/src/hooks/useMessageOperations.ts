import { useRef } from "react";
import { App as AntApp } from "antd";
import { api } from "@/api";
import {
  useConversationStore,
  useMessageStore,
  useArtifactStore,
  useTaskStore,
} from "@/store";
import type { ChatMessage, UploadedFile, MessageAttachment } from "@/types";
import {
  makeMessage,
  stripInternalAgentOutput,
  isLikelyArtifactRequest,
  participantName,
} from "@/lib/message";

export function useMessageOperations(currentUserName: string) {
  const { message } = AntApp.useApp();
  const { setBackgroundTasks } = useTaskStore();

  const refreshTasks = async () => {
    const tasks = await api.tasks();
    setBackgroundTasks(tasks);
  };

  const { conversations, activeId, updateConversations } =
    useConversationStore();
  const {
    appendHistoryMessage,
    replaceHistoryMessage,
    startStreamingMessage,
    updateStreamingContent,
    updateStreamingThinking,
    updateStreamingState,
    finishStreamingMessage,
    finishAllStreamingMessages,
    setHistoryMessages,
    setStreamState,
    updateLocalRunningConversationIds,
  } = useMessageStore();
  const { setArtifact } = useArtifactStore();

  const stopStreamRef = useRef<(() => void) | undefined>();

  const active = conversations.find((item) => item.id === activeId);

  const appendConversationStream = async (
    conversationId: string,
    _prompt: string,
  ) => {
    const targetConversation =
      conversations.find((item) => item.id === conversationId) ?? active;
    const agentParticipants =
      targetConversation?.participants.filter(
        (item) => item.participant_type === "agent" && item.agent_id,
      ) ?? [];
    const tempIdsByAgentId = new Map<string, string>();
    const tempIdsByAuthor = new Map<string, string>();

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

    /** 确保流式消息存在于 streamingMessages Map 中 */
    const ensureStreamingMessage = (
      messageId: string,
      author: string,
      agentId?: string,
    ) => {
      const { streamingMessages } = useMessageStore.getState();

      // 已存在，不做任何事
      if (streamingMessages.has(messageId)) return;

      // 查找临时消息并替换
      const tempId =
        (agentId && tempIdsByAgentId.get(agentId)) ||
        tempIdsByAuthor.get(author);
      if (tempId && streamingMessages.has(tempId)) {
        const tempMsg = streamingMessages.get(tempId)!;
        if (agentId) tempIdsByAgentId.set(agentId, messageId);
        tempIdsByAuthor.set(author, messageId);

        const { removeStreamingMessage } = useMessageStore.getState();
        removeStreamingMessage(tempId);
        startStreamingMessage({
          ...tempMsg,
          id: messageId,
          sender_id: agentId,
          author,
          rawContent: { ...(tempMsg.rawContent ?? {}), agent_id: agentId },
          streamState: "streaming",
        });
        return;
      }

      // 创建新消息（用后端提供的 messageId，确保和 delta 事件中的 ID 一致）
      startStreamingMessage({
        id: messageId,
        conversationId,
        role: "assistant",
        kind: "text",
        author,
        content: "",
        rawContent: agentId ? { agent_id: agentId } : {},
        streamState: "streaming",
        createdAt: new Date().toISOString(),
      });
    };

    /** 插入或更新最终消息（后端推送的完整消息） */
    const upsertFinalMessage = (incoming: ChatMessage) => {
      let normalized = normalizeIncomingMessage(incoming);
      const agentId =
        normalized.sender_id ||
        (normalized.rawContent?.agent_id as string | undefined);

      const {
        streamingMessages,
        historyMessages,
        updateStreamingState,
        replaceHistoryMessage,
      } = useMessageStore.getState();

      // 优先检查 streamingMessages：保留流式传输过程中已累积的内容字段
      if (streamingMessages.has(normalized.id)) {
        const existing = streamingMessages.get(normalized.id)!;
        // 后端 message:updated 可能只传了元数据（无 content/thinking），
        // 不要用它覆盖前端已收到的流式内容
        if (!normalized.content && existing.content) {
          normalized = { ...normalized, content: existing.content };
        }
        if (!normalized.thinking && existing.thinking) {
          normalized = { ...normalized, thinking: existing.thinking };
        }
        updateStreamingState(normalized.id, normalized);
        return;
      }

      // 检查 historyMessages
      const inHistory = historyMessages.some(
        (item) => item.id === normalized.id,
      );
      if (inHistory) {
        replaceHistoryMessage(normalized.id, normalized);
        return;
      }

      // 检查是否有临时消息需要替换
      const tempId =
        (agentId && tempIdsByAgentId.get(agentId)) ||
        tempIdsByAuthor.get(normalized.author);
      if (tempId && streamingMessages.has(tempId)) {
        if (agentId) tempIdsByAgentId.set(agentId, normalized.id);
        tempIdsByAuthor.set(normalized.author, normalized.id);

        const { removeStreamingMessage } = useMessageStore.getState();
        removeStreamingMessage(tempId);
        startStreamingMessage(normalized);
        return;
      }

      // 直接添加为历史消息
      appendHistoryMessage(normalized);
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
        rawContent: {
          agent_id: participant.agent_id,
          participant_id: participant.id,
        },
        streamState: "streaming",
      });
      tempIdsByAgentId.set(agentId, placeholder.id);
      tempIdsByAuthor.set(author, placeholder.id);
      startStreamingMessage(placeholder);
    }

    setStreamState("streaming");
    updateLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.add(conversationId);
      return next;
    });
    updateConversations((current) =>
      current.map((item) =>
        item.id === conversationId
          ? { ...item, updatedAt: new Date().toISOString(), unread: 0 }
          : item,
      ),
    );
    stopStreamRef.current = undefined;

    // delta 累积器（仅用于本地缓冲，不控制渲染频率）
    const latestContentById = new Map<string, string>();
    const latestThinkingById = new Map<string, string>();

    // 节流：用 requestAnimationFrame 批处理高频 SSE delta 更新，避免 React 渲染循环溢出
    let contentRafId = 0;
    let rawBuffer = "";
    let completedPreview = "";
    // 追踪当前消息上正在执行的工具调用
    const activeToolCalls = new Map<
      string,
      { toolName: string; toolCallId: string }
    >();
    let currentMessageId = "";

    const updateActiveToolCalls = (messageId: string) => {
      if (!messageId) return;
      const { streamingMessages } = useMessageStore.getState();
      const msg = streamingMessages.get(messageId);
      if (!msg) return;
      updateStreamingState(messageId, {
        rawContent: {
          ...msg.rawContent,
          _activeToolCalls: Array.from(activeToolCalls.values()),
        },
      });
    };

    try {
      await api.streamAssistantReply(conversationId, {
        onMessageStart: (payload) => {
          const messageId = String(
            payload.agent_message_id ||
              payload.message_id ||
              `stream-${Date.now()}`,
          );
          currentMessageId = messageId;
          const agentId = payload.agent_id
            ? String(payload.agent_id)
            : undefined;
          const author = String(
            payload.agent_name ||
              payload.sender_name ||
              (agentId ? "Agent" : "Assistant"),
          );
          ensureStreamingMessage(messageId, author, agentId);
          activeToolCalls.clear();
        },
        onDelta: (delta, payload) => {
          rawBuffer += delta;
          const messageId = String(
            payload.agent_message_id || payload.message_id || "",
          );
          if (messageId) currentMessageId = messageId;
          if (!messageId) return;
          ensureStreamingMessage(
            messageId,
            String(payload.agent_name || "Agent"),
            payload.agent_id ? String(payload.agent_id) : undefined,
          );
          // 累积到本地缓冲，直接 O(1) 更新 Map
          const existing = latestContentById.get(messageId) ?? "";
          const nextContent = existing + delta;
          latestContentById.set(messageId, nextContent);
          // 节流：避免高频 SSE delta 导致 React 渲染循环溢出
          if (contentRafId) return;
          contentRafId = requestAnimationFrame(() => {
            contentRafId = 0;
            for (const [id, content] of latestContentById) {
              updateStreamingContent(id, content);
            }
          });
        },
        onReasoningDelta: (delta, payload) => {
          const messageId = String(
            payload.agent_message_id || payload.message_id || "",
          );
          if (messageId) currentMessageId = messageId;
          if (!messageId) return;
          ensureStreamingMessage(
            messageId,
            String(payload.agent_name || "Agent"),
            payload.agent_id ? String(payload.agent_id) : undefined,
          );
          const existing = latestThinkingById.get(messageId) ?? "";
          const nextThinking = existing + delta;
          latestThinkingById.set(messageId, nextThinking);
          updateStreamingThinking(messageId, nextThinking);
        },
        onMessageUpdated: upsertFinalMessage,
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

          const { streamingMessages } = useMessageStore.getState();

          // 先批量清理所有 streaming 消息的内容和工具调用状态
          for (const [msgId, msg] of streamingMessages) {
            const cleaned =
              msg.role === "assistant" && msg.kind === "text"
                ? stripInternalAgentOutput(msg.content)
                : msg.content;
            updateStreamingState(msgId, {
              content: cleaned,
              rawContent: {
                ...msg.rawContent,
                _activeToolCalls: [],
              },
            });
          }

          // 将所有 streaming 消息归档到 history
          finishAllStreamingMessages();
        },
        onControl: (stop) => {
          stopStreamRef.current = stop;
        },
      });
      setStreamState("done");
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
        setHistoryMessages(
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
        updateConversations((current) =>
          current.map((item) =>
            item.id === conversationId
              ? {
                  ...item,
                  lastMessage: completedPreview,
                  updatedAt: new Date().toISOString(),
                }
              : item,
          ),
        );
      }
      if (freshArtifact) setArtifact(freshArtifact);
    } catch (error) {
      activeToolCalls.clear();
      const fallbackPreview =
        stripInternalAgentOutput(rawBuffer).slice(0, 120) || "reply failed";
      completedPreview = fallbackPreview;
      setStreamState("error");

      const { streamingMessages } = useMessageStore.getState();

      // 将所有 streaming 消息标记为 error 并归档
      for (const [msgId, msg] of streamingMessages) {
        updateStreamingState(msgId, {
          streamState: "error",
          content: msg.content || fallbackPreview,
          rawContent: { ...msg.rawContent, _activeToolCalls: [] },
        });
        finishStreamingMessage(msgId);
      }

      throw error;
    } finally {
      updateLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      if (completedPreview) {
        updateConversations((current) =>
          current.map((item) =>
            item.id === conversationId && item.lastMessage === "正在回答..."
              ? {
                  ...item,
                  lastMessage: completedPreview,
                  updatedAt: new Date().toISOString(),
                }
              : item,
          ),
        );
      }
      refreshTasks().catch(() => undefined);
    }
  };

  const stopStreaming = async () => {
    if (!activeId) return;
    stopStreamRef.current?.();
    stopStreamRef.current = undefined;
    setStreamState("done");
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

    const { streamingMessages } = useMessageStore.getState();

    // 将所有 streaming 消息标记为 done 并归档
    for (const [msgId, msg] of streamingMessages) {
      updateStreamingState(msgId, {
        streamState: "done",
        content: msg.content || "已停止接收本次回复。",
      });
      finishStreamingMessage(msgId);
    }

    await api.cancelAssistantReply(activeId).catch(() => undefined);
    await refreshTasks().catch(() => undefined);
    message.info("已停止本次响应");
  };

  const send = async (
    content: string,
    quoted?: ChatMessage,
    attachments: UploadedFile[] = [],
    thinkingEnabled?: boolean,
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
      rawContent: { text: content, attachments: localAttachments },
      attachments: localAttachments,
      quotedMessageId: quoted?.id,
    });
    appendHistoryMessage(localMessage);
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
    const streamPromise = appendConversationStream(
      conversationId,
      content,
    ).catch(() => setStreamState("error"));
    try {
      const userMessage = await api.sendMessage(
        conversationId,
        content,
        quoted?.id,
        attachments,
        thinkingEnabled,
      );

      replaceHistoryMessage(localMessage.id, userMessage);
      if (isLikelyArtifactRequest(content)) {
        const freshArtifact = await api
          .artifact(conversationId)
          .catch(() => undefined);
        if (freshArtifact) {
          setArtifact(freshArtifact);
          const { historyMessages } = useMessageStore.getState();
          const exists = historyMessages.some(
            (item) =>
              item.kind === "preview_card" &&
              item.rawContent?.artifact_id === freshArtifact.id,
          );
          if (!exists) {
            appendHistoryMessage(
              makeMessage({
                conversationId,
                role: "assistant",
                kind: "preview_card",
                author: "Artifact Agent",
                content: `预览产物：${freshArtifact.title}`,
                rawContent: { artifact_id: freshArtifact.id },
                streamState: "done",
              }),
            );
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
      stopStreamRef.current?.();
      void streamPromise;
      const { historyMessages } = useMessageStore.getState();
      const index = historyMessages.findIndex(
        (item) => item.id === localMessage.id,
      );
      if (index !== -1) {
        const { updateHistoryMessage } = useMessageStore.getState();
        updateHistoryMessage(localMessage.id, {
          kind: "error",
          content: `${content}\n\n发送失败：${error instanceof Error ? error.message : "网络异常"}`,
        });
      }
      message.error("消息发送失败");
    }
  };

  const regenerate = (source: ChatMessage) => {
    if (!activeId) return;
    appendConversationStream(
      activeId,
      `请重新生成这条回复：${source.content}`,
    ).catch(() => setStreamState("error"));
  };

  return { send, regenerate, stopStreaming };
}
