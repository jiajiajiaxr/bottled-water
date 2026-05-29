import { useRef } from "react";
import { App as AntApp } from "antd";
import { api } from "../api";
import {
  useConversationStore,
  useMessageStore,
  useArtifactStore,
  useTaskStore,
} from "../store";
import type { ChatMessage, UploadedFile, MessageAttachment, ToolEventRecord } from "../types";
import {
  makeMessage,
  stripInternalAgentOutput,
  isTaskRunning,
  participantName,
  isVisibleChatMessage,
} from "../lib/message";
import { mergeToolEvents, toolEventsFromMessage } from "../lib/toolEvents";

/** 批量触发更新：16ms 窗口内收到 delta 的消息 id 合并为一次 state 更新（约 60fps） */
function createDeltaBatcher(
  flush: (msgIds: string[]) => void,
  windowMs = 16,
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
  const { setBackgroundTasks } = useTaskStore();

  const refreshTasks = async () => {
    const tasks = await api.tasks();
    setBackgroundTasks(tasks);
  };

  const { conversations, activeId, updateConversations } =
    useConversationStore();
  const {
    updateMessages,
    updateMessageContent,
    updateMessageThinking,
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
    const pendingMessageIds = new Set<string>();
    const activeToolCalls = new Map<string, Map<string, ToolEventRecord>>();
    const toolEventsByMessageId = new Map<string, ToolEventRecord[]>();
    const isSingleAgentConversation = agentParticipants.length === 1;

    const isTerminalMessageStatus = (status?: string) =>
      ["completed", "failed", "cancelled", "error"].includes(
        String(status || "").toLowerCase(),
      );

    const clearConversationRunning = (streamState: "done" | "error" = "done") => {
      pendingMessageIds.clear();
      activeToolCalls.clear();
      updateLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      updateMessages((current) =>
        current.map((item) =>
          item.conversationId === conversationId && item.streamState === "streaming"
            ? {
                ...item,
                streamState,
                rawContent: { ...item.rawContent, _activeToolCalls: [] },
              }
            : item,
        ),
      );
    };

    const clearMessagePending = (messageId?: string) => {
      if (!messageId) return;
      pendingMessageIds.delete(messageId);
      activeToolCalls.delete(messageId);
      updateMessages((current) =>
        current.map((item) =>
          item.id === messageId
            ? {
                ...item,
                streamState: item.streamState === "streaming" ? "done" : item.streamState,
                rawContent: {
                  ...item.rawContent,
                  _activeToolCalls: [],
                  _toolEvents: toolEventsByMessageId.get(messageId) ?? toolEventsFromMessage(item),
                },
              }
            : item,
        ),
      );
      if (pendingMessageIds.size === 0 && isSingleAgentConversation) {
        updateLocalRunningConversationIds((current) => {
          const next = new Set(current);
          next.delete(conversationId);
          return next;
        });
      }
    };

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
      if (isTerminalMessageStatus(normalized.status)) {
        clearMessagePending(normalized.id);
      }
      const agentId =
        normalized.sender_id ||
        (normalized.rawContent?.agent_id as string | undefined);
      updateMessages((current) => {
        const withToolEvents = (target: ChatMessage | undefined) => {
          const mergedEvents = mergeToolEvents(
            target ? toolEventsFromMessage(target) : [],
            toolEventsFromMessage(normalized),
            toolEventsByMessageId.get(normalized.id) ?? [],
          );
          if (mergedEvents.length) toolEventsByMessageId.set(normalized.id, mergedEvents);
          return {
            ...normalized,
            toolEvents: mergedEvents,
            rawContent: {
              ...normalized.rawContent,
              _activeToolCalls: [],
              _toolEvents: mergedEvents,
            },
          };
        };
        if (current.some((item) => item.id === normalized.id)) {
          return current.map((item) =>
            item.id === normalized.id ? { ...item, ...withToolEvents(item) } : item,
          );
        }
        const tempId =
          (agentId && tempIdsByAgentId.get(agentId)) ||
          tempIdsByAuthor.get(normalized.author);
        if (tempId) {
          if (agentId) tempIdsByAgentId.set(agentId, normalized.id);
          tempIdsByAuthor.set(normalized.author, normalized.id);
          return current.map((item) =>
            item.id === tempId ? { ...item, ...withToolEvents(item) } : item,
          );
        }
        return [...current, withToolEvents(undefined)];
      });
    };

    const closeStreamControl = () => {
      stopStreamRef.current = undefined;
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

    // 批量 delta 处理器：16ms 窗口内有更新的消息合并为一次 state 更新
    const latestContentById = new Map<string, string>();
    const deltaBatcher = createDeltaBatcher((msgIds) => {
      for (const msgId of msgIds) {
        const fullContent = latestContentById.get(msgId) ?? "";
        updateMessageContent(msgId, fullContent);
      }
    });

    // 批量 reasoning delta 处理器
    const latestThinkingById = new Map<string, string>();
    const thinkingBatcher = createDeltaBatcher((msgIds) => {
      for (const msgId of msgIds) {
        const fullThinking = latestThinkingById.get(msgId) ?? "";
        updateMessageThinking(msgId, fullThinking);
      }
    });

    let rawBuffer = "";
    let completedPreview = "";
    // 追踪当前消息上正在执行的工具调用
    let currentMessageId = "";

    const updateToolState = (messageId: string) => {
      if (!messageId) return;
      updateMessages((current) =>
        current.map((item) =>
          item.id === messageId
            ? {
                ...item,
                rawContent: {
                  ...item.rawContent,
                  _activeToolCalls: Array.from(activeToolCalls.get(messageId)?.values() ?? []),
                  _toolEvents: toolEventsByMessageId.get(messageId) ?? toolEventsFromMessage(item),
                },
              }
            : item,
        ),
      );
    };
    const messageIdFromToolPayload = (payload: Record<string, unknown>) =>
      String(payload.agent_message_id || payload.message_id || currentMessageId || "");
    const toolEventFromPayload = (payload: Record<string, unknown>): ToolEventRecord => {
      const detail = payload.detail && typeof payload.detail === "object"
        ? (payload.detail as Record<string, unknown>)
        : payload;
      return {
        toolName: String(detail.tool_name || detail.toolName || payload.tool_name || ""),
        toolCallId: String(detail.tool_call_id || detail.toolCallId || payload.tool_call_id || ""),
        status: String(detail.status || payload.status || ""),
        exit_code: detail.exit_code as string | number | undefined,
        duration_ms: detail.duration_ms as string | number | undefined,
        stdout: typeof detail.stdout === "string" ? detail.stdout : undefined,
        stderr: typeof detail.stderr === "string" ? detail.stderr : undefined,
        summary: typeof detail.summary === "string" ? detail.summary : undefined,
        error: typeof detail.error === "string" ? detail.error : undefined,
      };
    };
    const finishConversationRunningState = () => {
      updateLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      const { backgroundTasks, setBackgroundTasks: setTasks } =
        useTaskStore.getState();
      const now = new Date().toISOString();
      setTasks(
        backgroundTasks.map((task) =>
          task.conversation_id === conversationId &&
          isTaskRunning(task.status)
            ? {
                ...task,
                status: "COMPLETED",
                progress: 100,
                updated_at: now,
              }
            : task,
        ),
      );
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
          pendingMessageIds.add(messageId);
          ensureStreamingMessage(messageId, author, agentId);
          activeToolCalls.delete(messageId);
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
          // 累积到 latestContentById，标记消息待更新
          const existing = latestContentById.get(messageId) ?? "";
          latestContentById.set(messageId, existing + delta);
          deltaBatcher.add(messageId);
        },
        onReasoningDelta: (delta, payload) => {
          const messageId = String(
            payload.agent_message_id || payload.message_id || "",
          );
          if (messageId) currentMessageId = messageId;
          if (!messageId) return;
          // 累积到 latestThinkingById，标记消息待更新
          const existing = latestThinkingById.get(messageId) ?? "";
          latestThinkingById.set(messageId, existing + delta);
          thinkingBatcher.add(messageId);
        },
        onMessageUpdated: upsertFinalMessage,
        onMessageStop: (payload) => {
          clearMessagePending(
            String(payload.agent_message_id || payload.message_id || ""),
          );
        },
        onMessageNew: (incoming) => {
          if (!isVisibleChatMessage(incoming)) return;
          if (incoming.kind === "preview_card" || incoming.kind === "event") {
            upsertFinalMessage(incoming);
          }
        },
        onToolCallStart: (payload) => {
          const messageId = messageIdFromToolPayload(payload);
          const event = toolEventFromPayload(payload);
          const toolName = event.toolName;
          const toolCallId = event.toolCallId || `${toolName}-${Date.now()}`;
          if (toolName && toolCallId) {
            const calls = activeToolCalls.get(messageId) ?? new Map<string, ToolEventRecord>();
            calls.set(toolCallId, { ...event, toolCallId, status: "running" });
            activeToolCalls.set(messageId, calls);
            updateToolState(messageId);
          }
        },
        onToolCallDone: (payload) => {
          const messageId = messageIdFromToolPayload(payload);
          const event = toolEventFromPayload(payload);
          const toolCallId = event.toolCallId;
          if (messageId && toolCallId) {
            activeToolCalls.get(messageId)?.delete(toolCallId);
            const mergedEvents = mergeToolEvents(
              toolEventsByMessageId.get(messageId) ?? [],
              [event],
            );
            toolEventsByMessageId.set(messageId, mergedEvents);
            updateToolState(messageId);
          }
        },
        onTaskStatusChanged: (task) => {
          const { backgroundTasks, setBackgroundTasks: setTasks } =
            useTaskStore.getState();
          const exists = backgroundTasks.some((item) => item.id === task.id);
          setTasks(
            exists
              ? backgroundTasks.map((item) => (item.id === task.id ? task : item))
              : [task, ...backgroundTasks],
          );
          if (
            task.conversation_id === conversationId &&
            !isTaskRunning(task.status)
          ) {
            updateLocalRunningConversationIds((current) => {
              const next = new Set(current);
              next.delete(conversationId);
              return next;
            });
          }
        },
        onWorkflowRunUpdated: (payload) => {
          const status = String(payload.status || "");
          updateConversations((current) =>
            current.map((item) =>
              item.id === conversationId
                ? {
                    ...item,
                    workflow_runtime: {
                      ...(item.workflow_runtime ?? {}),
                      ...(payload as NonNullable<typeof item.workflow_runtime>),
                    },
                  }
                : item,
            ),
          );
          if (
            ["completed", "failed", "cancelled"].includes(status.toLowerCase())
          ) {
            updateLocalRunningConversationIds((current) => {
              const next = new Set(current);
              next.delete(conversationId);
              return next;
            });
          }
        },
        onDone: () => {
          closeStreamControl();
          deltaBatcher.flushNow();
          thinkingBatcher.flushNow();
          clearConversationRunning("done");
          // 流结束时统一过滤内部输出并清空工具调用状态
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
                rawContent: {
                  ...item.rawContent,
                  _activeToolCalls: [],
                },
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
        const cleanMessages = freshMessages
          .filter(isVisibleChatMessage)
          .map((item) =>
            item.role === "assistant" && item.kind === "text"
              ? {
                  ...item,
                  content: stripInternalAgentOutput(item.content),
                  streamState: "done" as const,
                }
              : item,
          );
        setMessages(cleanMessages);
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
      activeToolCalls.clear();
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
                rawContent: { ...item.rawContent, _activeToolCalls: [] },
              }
            : item,
        ),
      );
      throw error;
    } finally {
      finishConversationRunningState();
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
    const conversationId = activeId;
    await api.cancelAssistantReply(conversationId).catch(() => undefined);
    await new Promise((resolve) => {
      window.setTimeout(resolve, 500);
    });
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
    updateConversations((current) =>
      current.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              lastMessage: "已停止本次响应",
              updatedAt: new Date().toISOString(),
              workflow_runtime: item.workflow_runtime
                ? { ...item.workflow_runtime, status: "cancelled" }
                : item.workflow_runtime,
            }
          : item,
      ),
    );
    updateMessages((current) =>
      current.map((item) =>
        item.conversationId === conversationId && item.streamState === "streaming"
          ? {
              ...item,
              status: "cancelled",
              streamState: "done",
              rawContent: { ...item.rawContent, _activeToolCalls: [] },
              content: item.content || "已停止接收本次回复。",
            }
          : item,
      ),
    );
    const { backgroundTasks, setBackgroundTasks: setTasks } =
      useTaskStore.getState();
    setTasks(
      backgroundTasks.map((task) =>
        task.conversation_id === conversationId && isTaskRunning(task.status)
          ? {
              ...task,
              status: "CANCELLED",
              progress: Math.min(task.progress ?? 0, 95),
              updated_at: new Date().toISOString(),
              output: { ...(task.output ?? {}), cancelled: true },
            }
          : task,
      ),
    );
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
        thinkingEnabled,
      );
      updateMessages((current) =>
        current.map((item) =>
          item.id === localMessage.id ? userMessage : item,
        ),
      );
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
