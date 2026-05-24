import { useRef } from "react";
import { App as AntApp } from "antd";
import { api } from "../api";
import {
  useConversationStore,
  useMessageStore,
  useArtifactStore,
} from "../store";
import { useBackgroundTaskPolling } from "./useBackgroundTaskPolling";
import type { ChatMessage, UploadedFile, MessageAttachment } from "../types";
import {
  makeMessage,
  stripInternalAgentOutput,
  isLikelyArtifactRequest,
  participantName,
} from "../lib/message";

/** 批量触发更新：50ms 窗口内收到 delta 的消息 id 合并为一次 state 更新 */
function createDeltaBatcher(
  flush: (msgIds: string[]) => void,
  windowMs = 50,
) {
  const pending = new Set<string>();
  let timer: ReturnType<typeof setTimeout> | undefined;

  const scheduleFlush = () => {
    if (timer) return;
    timer = setTimeout(() => {
      timer = undefined;
      if (!pending.size) return;
      const snapshot = Array.from(pending);
      pending.clear();
      flush(snapshot);
    }, windowMs);
  };

  return {
    add: (messageId: string) => {
      pending.add(messageId);
      scheduleFlush();
    },
    flushNow: () => {
      if (timer) {
        clearTimeout(timer);
        timer = undefined;
      }
      if (!pending.size) return;
      const snapshot = Array.from(pending);
      pending.clear();
      flush(snapshot);
    },
  };
}

export function useMessageOperations(currentUserName: string) {
  const { message } = AntApp.useApp();
  const { loadBackgroundTasks } = useBackgroundTaskPolling();

  const { conversations, activeId, updateConversations } =
    useConversationStore();
  const {
    updateMessages,
    updateMessageContent,
    setMessages,
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

    const ensureStreamingMessage = (
      messageId: string,
      author: string,
      agentId?: string,
    ) => {
      updateMessages((current) => {
        if (current.some((item) => item.id === messageId)) return current;
        const tempId =
          (agentId && tempIdsByAgentId.get(agentId)) ||
          tempIdsByAuthor.get(author);
        if (tempId) {
          if (agentId) tempIdsByAgentId.set(agentId, messageId);
          tempIdsByAuthor.set(author, messageId);
          return current.map((item) =>
            item.id === tempId
              ? {
                  ...item,
                  id: messageId,
                  sender_id: agentId,
                  author,
                  rawContent: { ...(item.rawContent ?? {}), agent_id: agentId },
                  streamState: "streaming",
                }
              : item,
          );
        }
        return [
          ...current,
          makeMessage({
            conversationId,
            role: "assistant",
            kind: "text",
            author,
            content: "",
            rawContent: agentId ? { agent_id: agentId } : {},
            streamState: "streaming",
          }),
        ].map((item) =>
          item.id.startsWith("local-") &&
          item.author === author &&
          !item.content
            ? { ...item, id: messageId }
            : item,
        );
      });
    };

    const upsertFinalMessage = (incoming: ChatMessage) => {
      const normalized = normalizeIncomingMessage(incoming);
      const agentId =
        normalized.sender_id ||
        (normalized.rawContent?.agent_id as string | undefined);
      updateMessages((current) => {
        if (current.some((item) => item.id === normalized.id)) {
          return current.map((item) =>
            item.id === normalized.id ? { ...item, ...normalized } : item,
          );
        }
        const tempId =
          (agentId && tempIdsByAgentId.get(agentId)) ||
          tempIdsByAuthor.get(normalized.author);
        if (tempId) {
          if (agentId) tempIdsByAgentId.set(agentId, normalized.id);
          tempIdsByAuthor.set(normalized.author, normalized.id);
          return current.map((item) =>
            item.id === tempId ? { ...item, ...normalized } : item,
          );
        }
        return [...current, normalized];
      });
    };

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
      updateMessages((current) => [...current, placeholder]);
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

    // 批量 delta 处理器：50ms 窗口内有更新的消息合并为一次 state 更新
    const latestContentById = new Map<string, string>();
    const deltaBatcher = createDeltaBatcher((msgIds) => {
      for (const msgId of msgIds) {
        const fullContent = latestContentById.get(msgId) ?? "";
        updateMessageContent(msgId, fullContent);
      }
    });

    let rawBuffer = "";
    let completedPreview = "";
    try {
      await api.streamAssistantReply(conversationId, {
        onMessageStart: (payload) => {
          const messageId = String(
            payload.agent_message_id ||
              payload.message_id ||
              `stream-${Date.now()}`,
          );
          const agentId = payload.agent_id
            ? String(payload.agent_id)
            : undefined;
          const author = String(
            payload.agent_name ||
              payload.sender_name ||
              (agentId ? "Agent" : "Assistant"),
          );
          ensureStreamingMessage(messageId, author, agentId);
        },
        onDelta: (delta, payload) => {
          rawBuffer += delta;
          const messageId = String(
            payload.agent_message_id || payload.message_id || "",
          );
          if (!messageId) return;
          ensureStreamingMessage(
            messageId,
            String(payload.agent_name || "Agent"),
            payload.agent_id ? String(payload.agent_id) : undefined,
          );
          // 累积到 latestContentById，标记消息待更新
          const existing = latestContentById.get(messageId) ?? "";
          latestContentById.set(messageId, existing + delta);
          deltaBatcher.add(messageId);
        },
        onMessageUpdated: upsertFinalMessage,
        onMessageNew: (incoming) => {
          if (incoming.kind === "preview_card") upsertFinalMessage(incoming);
        },
        onDone: () => {
          deltaBatcher.flushNow();
          // 流结束时统一过滤内部输出
          updateMessages((current) =>
            current.map((item) => {
              if (item.streamState !== "streaming") return item;
              const cleaned =
                item.role === "assistant" && item.kind === "text"
                  ? stripInternalAgentOutput(item.content)
                  : item.content;
              return {
                ...item,
                content: cleaned,
                streamState: "done" as const,
              };
            }),
          );
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
      deltaBatcher.flushNow();
      const fallbackPreview =
        stripInternalAgentOutput(rawBuffer).slice(0, 120) || "reply failed";
      completedPreview = fallbackPreview;
      setStreamState("error");
      updateMessages((current) =>
        current.map((item) =>
          item.streamState === "streaming"
            ? {
                ...item,
                streamState: "error",
                content: item.content || fallbackPreview,
              }
            : item,
        ),
      );
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
      loadBackgroundTasks().catch(() => undefined);
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
    updateMessages((current) =>
      current.map((item) =>
        item.streamState === "streaming"
          ? {
              ...item,
              streamState: "done",
              content: item.content || "已停止接收本次回复。",
            }
          : item,
      ),
    );
    await api.cancelAssistantReply(activeId).catch(() => undefined);
    await loadBackgroundTasks().catch(() => undefined);
    message.info("已停止本次响应");
  };

  const send = async (
    content: string,
    quoted?: ChatMessage,
    attachments: UploadedFile[] = [],
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
    updateMessages((current) => [...current, localMessage]);
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
      );
      updateMessages((current) =>
        current.map((item) =>
          item.id === localMessage.id ? userMessage : item,
        ),
      );
      if (isLikelyArtifactRequest(content)) {
        const freshArtifact = await api
          .artifact(conversationId)
          .catch(() => undefined);
        if (freshArtifact) {
          setArtifact(freshArtifact);
          updateMessages((current) => {
            const exists = current.some(
              (item) =>
                item.kind === "preview_card" &&
                item.rawContent?.artifact_id === freshArtifact.id,
            );
            if (exists) return current;
            return [
              ...current,
              makeMessage({
                conversationId,
                role: "assistant",
                kind: "preview_card",
                author: "Artifact Agent",
                content: `预览产物：${freshArtifact.title}`,
                rawContent: { artifact_id: freshArtifact.id },
                streamState: "done",
              }),
            ];
          });
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
      updateMessages((current) =>
        current.map((item) =>
          item.id === localMessage.id
            ? {
                ...item,
                kind: "error",
                content: `${content}\n\n发送失败：${error instanceof Error ? error.message : "网络异常"}`,
              }
            : item,
        ),
      );
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
