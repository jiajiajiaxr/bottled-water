import { App as AntApp } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import {
  useUIStore,
  useAgentStore,
  useWorkspaceStore,
  useTaskStore,
  useArtifactStore,
  useConversationStore,
  useMessageStore,
} from "../../store";
import { WorkbenchLayout } from "./WorkbenchLayout";
import { WorkbenchDrawers } from "./WorkbenchDrawers";
import type {
  ChatMessage,
  Conversation,
  MessageAttachment,
  UploadedFile,
  User,
  WorkspaceArtifact,
} from "../../types";
import {
  CONVERSATION_CATEGORY_OPTIONS,
  LEGACY_DEFAULT_CONVERSATION_CATEGORIES,
  mergeConversationCategories,
} from "../../lib/conversation";
import {
  makeMessage,
  stripInternalAgentOutput,
  isTaskRunning,
  isLikelyArtifactRequest,
  participantName,
} from "../../lib/message";

export function Workbench({
  user,
  onLogout,
  routeWorkspaceId,
  routeConversationId,
  routeTab = "chat",
  onRouteChange,
  onRouteTabChange,
}: {
  user: User;
  onLogout: () => void;
  routeWorkspaceId?: string;
  routeConversationId?: string;
  routeTab?: string;
  onRouteChange: (
    workspaceId?: string,
    conversationId?: string,
    options?: { replace?: boolean },
  ) => void;
  onRouteTabChange: (
    tab: "chat" | "agents" | "workspace" | "settings",
    options?: { replace?: boolean },
  ) => void;
}) {
  const [currentUser, setCurrentUser] = useState(user);
  const {
    messages,
    setMessages,
    streamState,
    setStreamState,
    localRunningConversationIds,
    updateMessages,
    updateLocalRunningConversationIds,
  } = useMessageStore();
  const {
    conversations,
    setConversations,
    activeId,
    setActiveId,
    conversationCategories,
    setConversationCategories,
    loadingMessages,
    setLoadingMessages,
    updateConversations,
  } = useConversationStore();
  const {
    artifact,
    setArtifact,
    deployment,
    setDeployment,
    files,
    setFiles,
    knowledgeBases,
    setKnowledgeBases,
  } = useArtifactStore();
  const { agents, setAgents, addAgent, updateAgent, removeAgent } =
    useAgentStore();
  const { backgroundTasks, setBackgroundTasks } = useTaskStore();
  const {
    workspaces,
    setWorkspaces,
    activeWorkspaceId,
    setActiveWorkspaceId,
    addWorkspace,
    updateWorkspace,
  } = useWorkspaceStore();
  const {
    agentDrawerOpen,
    workspacesOpen,
    globalSettingsOpen,
    conversationSettingsOpen,
    membersOpen,
    createOpen,
    artifactPanelOpen,
    setAgentDrawerOpen,
    setWorkspacesOpen,
    setGlobalSettingsOpen,
    setConversationSettingsOpen,
    setMembersOpen,
    setCreateOpen,
    setArtifactPanelOpen,
  } = useUIStore();
  const stopStreamRef = useRef<(() => void) | undefined>();
  const { message } = AntApp.useApp();

  const active = conversations.find((item) => item.id === activeId);
  const activeWorkspace =
    workspaces.find((workspace) => workspace.id === activeWorkspaceId) ??
    workspaces[0];
  const currentConversationIds = useMemo(
    () => new Set(conversations.map((item) => item.id)),
    [conversations],
  );
  const visibleBackgroundTasks = useMemo(
    () =>
      backgroundTasks.filter(
        (task) =>
          !task.conversation_id ||
          currentConversationIds.has(task.conversation_id),
      ),
    [backgroundTasks, currentConversationIds],
  );
  const runningConversationIds = useMemo(() => {
    const next = new Set(localRunningConversationIds);
    backgroundTasks.forEach((task) => {
      if (task.conversation_id && isTaskRunning(task.status))
        next.add(task.conversation_id);
    });
    return next;
  }, [backgroundTasks, localRunningConversationIds]);
  const categoryStorageKey = useMemo(
    () => `agenthub:conversation-categories:${activeWorkspaceId ?? "default"}`,
    [activeWorkspaceId],
  );
  const categoryNamesFromConversations = useMemo(
    () =>
      conversations.map((item) => item.folder || item.category || "Default"),
    [conversations],
  );

  const navigateToConversation = (
    workspaceId?: string,
    conversationId?: string,
    replace = false,
  ) => {
    onRouteChange(workspaceId, conversationId, { replace });
  };

  const selectWorkspace = (workspaceId?: string, replace = false) => {
    if (!workspaceId) return;
    setActiveWorkspaceId(workspaceId);
    setActiveId(undefined);
    navigateToConversation(workspaceId, undefined, replace);
  };

  const selectConversation = (conversationId?: string, replace = false) => {
    if (!conversationId) return;
    const target = conversations.find((item) => item.id === conversationId);
    const workspaceId =
      target?.workspace_id || activeWorkspaceId || activeWorkspace?.id;
    setActiveId(conversationId);
    navigateToConversation(workspaceId, conversationId, replace);
  };

  const openMainTab = (tab: "agents" | "workspace" | "settings") => {
    setAgentDrawerOpen(tab === "agents");
    setWorkspacesOpen(tab === "workspace");
    setGlobalSettingsOpen(tab === "settings");
    onRouteTabChange(tab);
  };

  const closeMainTab = (tab: "agents" | "workspace" | "settings") => {
    if (tab === "agents") setAgentDrawerOpen(false);
    if (tab === "workspace") setWorkspacesOpen(false);
    if (tab === "settings") setGlobalSettingsOpen(false);
    if (routeTab === tab) onRouteTabChange("chat");
  };

  const saveConversationCategories = (nextCategories: string[]) => {
    const merged = mergeConversationCategories(
      CONVERSATION_CATEGORY_OPTIONS,
      nextCategories,
    );
    setConversationCategories(merged);
    window.localStorage.setItem(
      categoryStorageKey,
      JSON.stringify({ version: 2, items: merged }),
    );
  };

  const addConversationCategory = (name: string) => {
    saveConversationCategories([...conversationCategories, name]);
    message.success(`分类「${name}」已创建`);
  };

  const loadAgents = async () => setAgents(await api.agents());
  const loadBackgroundTasks = useCallback(async () => {
    const tasks = await api.tasks();
    setBackgroundTasks(tasks);
  }, [setBackgroundTasks]);

  useEffect(() => {
    setCurrentUser(user);
  }, [user]);

  useEffect(() => {
    let stored: string[] = [];
    try {
      const raw = window.localStorage.getItem(categoryStorageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      if (Array.isArray(parsed)) {
        stored = parsed
          .map(String)
          .filter((name) => !LEGACY_DEFAULT_CONVERSATION_CATEGORIES.has(name));
      } else if (parsed && Array.isArray(parsed.items)) {
        stored = parsed.items.map(String);
      }
    } catch {
      stored = [];
    }
    setConversationCategories(
      mergeConversationCategories(CONVERSATION_CATEGORY_OPTIONS, stored),
    );
  }, [categoryStorageKey, setConversationCategories]);

  useEffect(() => {
    setConversationCategories(
      mergeConversationCategories(
        CONVERSATION_CATEGORY_OPTIONS,
        conversationCategories,
        categoryNamesFromConversations,
      ),
    );
  }, [categoryNamesFromConversations, conversationCategories, setConversationCategories]);

  useEffect(() => {
    Promise.all([api.agents(), api.knowledgeBases(), api.workspaces()]).then(
      ([nextAgents, kbs, nextWorkspaces]) => {
        setAgents(nextAgents);
        setKnowledgeBases(kbs);
        setWorkspaces(nextWorkspaces);
        const routeWorkspace = nextWorkspaces.find(
          (workspace) => workspace.id === routeWorkspaceId,
        );
        const nextWorkspaceId = routeWorkspace?.id ?? nextWorkspaces[0]?.id;
        if (nextWorkspaceId) {
          setActiveWorkspaceId(nextWorkspaceId);
          if (!routeWorkspaceId || routeWorkspaceId !== nextWorkspaceId)
            navigateToConversation(nextWorkspaceId, undefined, true);
        }
      },
    );
    loadBackgroundTasks().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!workspaces.length) return;
    const routeWorkspace = routeWorkspaceId
      ? workspaces.find((workspace) => workspace.id === routeWorkspaceId)
      : undefined;
    if (routeWorkspace) {
      if (activeWorkspaceId !== routeWorkspace.id) {
        setActiveWorkspaceId(routeWorkspace.id);
        setActiveId(undefined);
      }
      return;
    }
    const fallbackId =
      activeWorkspaceId &&
      workspaces.some((workspace) => workspace.id === activeWorkspaceId)
        ? activeWorkspaceId
        : workspaces[0]?.id;
    if (fallbackId) {
      if (activeWorkspaceId !== fallbackId) setActiveWorkspaceId(fallbackId);
      navigateToConversation(fallbackId, undefined, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeWorkspaceId, workspaces, activeWorkspaceId]);

  useEffect(() => {
    setAgentDrawerOpen(routeTab === "agents");
    setWorkspacesOpen(routeTab === "workspace");
    setGlobalSettingsOpen(routeTab === "settings");
  }, [routeTab, setAgentDrawerOpen, setWorkspacesOpen, setGlobalSettingsOpen]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadBackgroundTasks().catch(() => undefined);
    }, 3500);
    return () => window.clearInterval(timer);
  }, [loadBackgroundTasks]);

  useEffect(() => {
    if (!activeWorkspaceId && workspaces.length) return;
    let cancelled = false;
    setConversations([]);
    setActiveId(undefined);
    setMessages([]);
    setArtifact(undefined);
    setArtifactPanelOpen(false);
    api.conversations(activeWorkspaceId).then((items) => {
      if (!cancelled) setConversations(items);
    });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, workspaces.length, setArtifactPanelOpen, setArtifact, setActiveId, setConversations, setMessages]);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    const scopedConversations = conversations.filter(
      (item) => (item.workspace_id || undefined) === activeWorkspaceId,
    );
    if (!scopedConversations.length) {
      setActiveId(undefined);
      if (routeConversationId)
        navigateToConversation(activeWorkspaceId, undefined, true);
      return;
    }
    const routeConversation = routeConversationId
      ? scopedConversations.find((item) => item.id === routeConversationId)
      : undefined;
    const currentConversation = activeId
      ? scopedConversations.find((item) => item.id === activeId)
      : undefined;
    const nextConversation =
      routeConversation ??
      currentConversation ??
      scopedConversations.find((item) => !item.archived) ??
      scopedConversations[0];
    if (!nextConversation) return;
    if (activeId !== nextConversation.id) setActiveId(nextConversation.id);
    const workspaceId = nextConversation.workspace_id || activeWorkspaceId;
    if (
      routeWorkspaceId !== workspaceId ||
      routeConversationId !== nextConversation.id
    ) {
      navigateToConversation(workspaceId, nextConversation.id, true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    activeWorkspaceId,
    activeId,
    conversations,
    routeConversationId,
    routeWorkspaceId,
  ]);

  useEffect(() => {
    if (!activeId) return;
    setArtifactPanelOpen(false);
    setLoadingMessages(true);
    Promise.all([
      api.messages(activeId),
      api.artifact(activeId),
      api.files(activeId),
    ])
      .then(([nextMessages, nextArtifact, nextFiles]) => {
        setMessages(nextMessages);
        setArtifact(nextArtifact);
        setFiles(nextFiles);
      })
      .finally(() => setLoadingMessages(false));
  }, [activeId, setArtifactPanelOpen, setArtifact, setFiles, setLoadingMessages, setMessages]);

  const patchConversation = async (
    item: Conversation,
    patch: Partial<Conversation>,
  ) => {
    const updated = await api.updateConversation(item.id, patch);
    const nextCategory =
      patch.folder || patch.category || updated.folder || updated.category;
    if (nextCategory)
      saveConversationCategories([...conversationCategories, nextCategory]);
    updateConversations((current) =>
      current.map((conversation) =>
        conversation.id === item.id
          ? { ...conversation, ...updated }
          : conversation,
      ),
    );
  };

  const createConversation = async (payload: {
    title?: string;
    agentIds: string[];
    group: boolean;
    masterEnabled: boolean;
    folder: string;
  }) => {
    const created = await api.createConversationWithAgents({
      chat_type: payload.group ? "group" : "single",
      title: payload.title,
      participant_agent_ids: payload.agentIds,
      master_enabled: payload.masterEnabled,
      folder: payload.folder,
      category: payload.folder,
      workspace_id: activeWorkspaceId,
    });
    saveConversationCategories([...conversationCategories, payload.folder]);
    updateConversations((current) => [created, ...current]);
    setActiveId(created.id);
    navigateToConversation(
      created.workspace_id || activeWorkspaceId,
      created.id,
    );
    setMessages([]);
    setCreateOpen({ open: false, group: false });
    message.success(payload.group ? "群聊已创建" : "会话已创建");
  };

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
          updateMessages((current) =>
            current.map((item) =>
              item.id === messageId
                ? {
                    ...item,
                    content: stripInternalAgentOutput(
                      `${item.content}${delta}`,
                    ),
                    streamState: "streaming",
                  }
                : item,
            ),
          );
        },
        onMessageUpdated: upsertFinalMessage,
        onMessageNew: (incoming) => {
          if (incoming.kind === "preview_card") upsertFinalMessage(incoming);
        },
        onDone: () => {
          updateMessages((current) =>
            current.map((item) =>
              item.streamState === "streaming"
                ? { ...item, streamState: "done" }
                : item,
            ),
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
      author: currentUser.name,
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

  const saveArtifact = async (next: WorkspaceArtifact) => {
    const saved = await api.saveArtifact(next);
    setArtifact(saved);
    message.success("产物已保存");
  };

  const deploy = async () => {
    if (!activeId) return;
    setDeployment({
      id: "pending",
      status: "building",
      commit: "pending",
      updatedAt: new Date().toISOString(),
    });
    const result = await api.deploy(activeId, artifact?.id);
    setDeployment(result);
    message.success("部署任务已提交");
  };

  const uploadFile = async (file: File) => {
    const uploaded = await api.uploadFile(file, activeId);
    setFiles([uploaded, ...files]);
    message.success("文件已加入输入框，发送后会进入模型上下文");
    return uploaded;
  };

  const openArtifactPreview = async (source?: ChatMessage) => {
    if (!activeId) return;
    const artifactId =
      typeof source?.rawContent?.artifact_id === "string"
        ? source.rawContent.artifact_id
        : undefined;
    const current =
      (artifactId ? await api.artifactById(artifactId) : undefined) ??
      artifact ??
      (await api.artifact(activeId));
    const nextArtifact =
      current ??
      (source?.kind === "preview_card"
        ? {
            id: artifactId ?? `local-${activeId}`,
            conversationId: activeId,
            title:
              source.content.replace(/^预览产物[:：]\s*/, "") ||
              "AgentHub artifact",
            language: "html",
            code: "<main><h1>Artifact preview</h1><p>产物索引已恢复，请刷新或重新生成以查看完整文件。</p></main>",
            previousCode: "",
            updatedAt: new Date().toISOString(),
          }
        : undefined);
    if (!nextArtifact) {
      message.warning("当前会话还没有可预览产物");
      return;
    }
    setArtifact(nextArtifact);
    setArtifactPanelOpen(true);
  };

  return (
    <>
      <WorkbenchLayout
        currentUser={currentUser}
        onLogout={onLogout}
        workspaces={workspaces}
        activeWorkspace={activeWorkspace}
        activeWorkspaceId={activeWorkspaceId}
        selectWorkspace={selectWorkspace}
        openMainTab={openMainTab}
        conversations={conversations}
        activeId={activeId}
        active={active}
        conversationCategories={conversationCategories}
        selectConversation={selectConversation}
        setCreateOpen={setCreateOpen}
        addConversationCategory={addConversationCategory}
        patchConversation={patchConversation}
        updateConversations={updateConversations}
        setActiveId={setActiveId}
        navigateToConversation={navigateToConversation}
        messages={messages}
        loadingMessages={loadingMessages}
        streamState={streamState}
        send={send}
        regenerate={regenerate}
        stopStreaming={stopStreaming}
        setMembersOpen={setMembersOpen}
        setConversationSettingsOpen={setConversationSettingsOpen}
        uploadFile={uploadFile}
        artifactPanelOpen={artifactPanelOpen}
        artifact={artifact}
        deployment={deployment}
        files={files}
        knowledgeBases={knowledgeBases}
        setArtifactPanelOpen={setArtifactPanelOpen}
        saveArtifact={saveArtifact}
        deploy={deploy}
        setKnowledgeBases={setKnowledgeBases}
        openArtifactPreview={openArtifactPreview}
        visibleBackgroundTasks={visibleBackgroundTasks}
        loadBackgroundTasks={loadBackgroundTasks}
        updateLocalRunningConversationIds={updateLocalRunningConversationIds}
        runningConversationIds={runningConversationIds}
      />
      <WorkbenchDrawers
        agentDrawerOpen={agentDrawerOpen}
        agents={agents}
        onCloseAgentDrawer={() => closeMainTab('agents')}
        onRefreshAgents={loadAgents}
        onCreateAgent={addAgent}
        onUpdateAgent={(agent) => updateAgent(agent.id, agent)}
        onDeleteAgent={async (agent) => {
          await api.deleteAgent(agent.id);
          removeAgent(agent.id);
        }}
        onTestAgent={async (agentId, text) =>
          (await api.testAgent(agentId, text)).response
        }
        membersOpen={membersOpen}
        activeConversation={active}
        activeConversationId={activeId}
        onCloseMembers={() => setMembersOpen(false)}
        onUpdateConversations={updateConversations}
        conversationSettingsOpen={conversationSettingsOpen}
        onCloseConversationSettings={() => setConversationSettingsOpen(false)}
        conversationCategories={conversationCategories}
        onPatchConversation={patchConversation}
        createOpen={createOpen}
        onCancelCreate={() => setCreateOpen({ open: false, group: false })}
        onCreateConversation={createConversation}
        globalSettingsOpen={globalSettingsOpen}
        currentUser={currentUser}
        onCloseGlobalSettings={() => closeMainTab('settings')}
        onUserUpdated={(nextUser) => setCurrentUser(nextUser)}
        workspacesOpen={workspacesOpen}
        workspaces={workspaces}
        onCloseWorkspaces={() => closeMainTab('workspace')}
        onLoadProjects={api.projects}
        onSetActiveWorkspaceId={setActiveWorkspaceId}
        onNavigateToConversation={navigateToConversation}
        onAddWorkspace={addWorkspace}
        onUpdateWorkspace={updateWorkspace}
      />
    </>
  );
}
