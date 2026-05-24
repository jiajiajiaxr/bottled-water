import {
  App as AntApp,
  Avatar,
  Button,
  Layout,
  Modal,
  Select,
  Space,
  Typography,
} from "antd";
import {
  AppstoreOutlined,
  RobotOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../api";
import { BackgroundTasksButton } from "./BackgroundTasksButton";
import { CreateConversationModal } from "../../features/chat/components/CreateConversationModal";
import { MembersDrawer } from "../../features/chat/components/drawers/MembersDrawer";
import { ConversationSettingsDrawer } from "../../features/chat/components/drawers/ConversationSettingsDrawer";
import { ConversationSidebar } from "../../features/chat/components/ConversationSidebar";
import { ChatPanel } from "../../features/chat/components/ChatPanel";
import { AgentDirectoryDrawer } from "../../features/agents/components/AgentDirectoryDrawer";
import { WorkspacesDrawer } from "../../features/workspace/components/WorkspacesDrawer";
import { GlobalSettingsDrawer } from "../../features/settings/components/GlobalSettingsDrawer";
import { PreviewPanel } from "../../features/preview/components/PreviewPanel";
import { PlatformControlDrawer } from "../../features/platform/components/PlatformControlDrawer";
import type {
  Agent,
  AgentTask,
  ChatMessage,
  Conversation,
  Deployment,
  KnowledgeBase,
  MessageAttachment,
  UploadedFile,
  User,
  Workspace,
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

const { Text } = Typography;

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
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [artifact, setArtifact] = useState<WorkspaceArtifact>();
  const [artifactPanelOpen, setArtifactPanelOpen] = useState(false);
  const [deployment, setDeployment] = useState<Deployment>();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [backgroundTasks, setBackgroundTasks] = useState<AgentTask[]>([]);
  const [localRunningConversationIds, setLocalRunningConversationIds] =
    useState<Set<string>>(() => new Set());
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>();
  const [conversationCategories, setConversationCategories] = useState<
    string[]
  >(CONVERSATION_CATEGORY_OPTIONS);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [streamState, setStreamState] = useState<
    "idle" | "streaming" | "done" | "error"
  >("idle");
  const [agentDrawerOpen, setAgentDrawerOpen] = useState(false);
  const [workspacesOpen, setWorkspacesOpen] = useState(false);
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
  const [conversationSettingsOpen, setConversationSettingsOpen] =
    useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState<{
    open: boolean;
    group: boolean;
  }>({ open: false, group: false });
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
  const loadBackgroundTasks = async () => {
    const tasks = await api.tasks();
    setBackgroundTasks(tasks);
  };

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
  }, [categoryStorageKey]);

  useEffect(() => {
    setConversationCategories((current) =>
      mergeConversationCategories(
        CONVERSATION_CATEGORY_OPTIONS,
        current,
        categoryNamesFromConversations,
      ),
    );
  }, [categoryNamesFromConversations]);

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
  }, [routeWorkspaceId, workspaces, activeWorkspaceId]);

  useEffect(() => {
    setAgentDrawerOpen(routeTab === "agents");
    setWorkspacesOpen(routeTab === "workspace");
    setGlobalSettingsOpen(routeTab === "settings");
  }, [routeTab]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadBackgroundTasks().catch(() => undefined);
    }, 3500);
    return () => window.clearInterval(timer);
  }, []);

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
  }, [activeWorkspaceId, workspaces.length]);

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
  }, [activeId]);

  const patchConversation = async (
    item: Conversation,
    patch: Partial<Conversation>,
  ) => {
    const updated = await api.updateConversation(item.id, patch);
    const nextCategory =
      patch.folder || patch.category || updated.folder || updated.category;
    if (nextCategory)
      saveConversationCategories([...conversationCategories, nextCategory]);
    setConversations((current) =>
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
    setConversations((current) => [created, ...current]);
    setActiveId(created.id);
    navigateToConversation(
      created.workspace_id || activeWorkspaceId,
      created.id,
    );
    setMessages([]);
    setCreateOpen({ open: false, group: false });
    message.success(payload.group ? "群聊已创建" : "会话已创建");
  };

  const appendAssistantStream = async (
    conversationId: string,
    prompt: string,
  ) => {
    const assistant = makeMessage({
      conversationId,
      role: "assistant",
      kind: "text",
      author: "Master Agent",
      content: "",
      streamState: "streaming",
    });
    setMessages((current) => [...current, assistant]);
    setStreamState("streaming");
    setLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.add(conversationId);
      return next;
    });
    setConversations((current) =>
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
      await api.streamAssistantReply(
        conversationId,
        (delta) => {
          rawBuffer += delta;
          const visible = stripInternalAgentOutput(rawBuffer);
          setMessages((current) =>
            current.map((item) =>
              item.id === assistant.id ? { ...item, content: visible } : item,
            ),
          );
        },
        () => {
          setMessages((current) =>
            current.map((item) =>
              item.id === assistant.id
                ? { ...item, streamState: "done" }
                : item,
            ),
          );
        },
        (stop) => {
          stopStreamRef.current = stop;
        },
      );
      setMessages((current) =>
        current.map((item) =>
          item.id === assistant.id ? { ...item, streamState: "done" } : item,
        ),
      );
      setStreamState("done");
      const [freshMessages, freshArtifact] = await Promise.all([
        api.messages(conversationId),
        api.artifact(conversationId),
      ]).catch(() => [undefined, undefined]);
      if (freshMessages) {
        const cleanMessages = freshMessages.map((item) =>
          item.role === "assistant" && item.kind === "text"
            ? { ...item, content: stripInternalAgentOutput(item.content) }
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
        const previewText =
          stripInternalAgentOutput(lastAssistant?.content ?? rawBuffer) ||
          "已完成";
        completedPreview = previewText.slice(0, 120);
        setConversations((current) =>
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
        stripInternalAgentOutput(rawBuffer).slice(0, 120) ||
        "回复暂未完成，请稍后刷新。";
      completedPreview = fallbackPreview;
      setStreamState("error");
      setMessages((current) =>
        current.map((item) =>
          item.id === assistant.id
            ? {
                ...item,
                streamState: "error",
                content: stripInternalAgentOutput(rawBuffer) || fallbackPreview,
              }
            : item,
        ),
      );
      throw error;
    } finally {
      setLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      if (completedPreview) {
        setConversations((current) =>
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

  const appendConversationStream = async (
    conversationId: string,
    prompt: string,
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
      setMessages((current) => {
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
      setMessages((current) => {
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
      setMessages((current) => [...current, placeholder]);
    }

    setStreamState("streaming");
    setLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.add(conversationId);
      return next;
    });
    setConversations((current) =>
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
          setMessages((current) =>
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
          setMessages((current) =>
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
        setConversations((current) =>
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
      setMessages((current) =>
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
      setLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      if (completedPreview) {
        setConversations((current) =>
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
    setLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.delete(activeId);
      return next;
    });
    setConversations((current) =>
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
    setMessages((current) =>
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
    setMessages((current) => [...current, localMessage]);
    setConversations((current) =>
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
      setMessages((current) =>
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
          setMessages((current) => {
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
          setConversations((current) =>
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
      setMessages((current) =>
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
    setFiles((current) => [uploaded, ...current]);
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
    <Layout className="workbench">
      <ConversationSidebar
        conversations={conversations}
        activeId={activeId}
        runningConversationIds={runningConversationIds}
        categoryOptions={conversationCategories}
        onSelect={selectConversation}
        onCreate={(group) => setCreateOpen({ open: true, group })}
        onCreateCategory={addConversationCategory}
        onTogglePin={(item) =>
          patchConversation(item, { pinned: !item.pinned })
        }
        onToggleArchive={(item) =>
          patchConversation(item, { archived: !item.archived })
        }
        onEdit={(item, patch) => patchConversation(item, patch)}
        onDelete={(item) => {
          Modal.confirm({
            title: "删除归档会话",
            content: `确认删除「${item.title}」？删除后会从列表移除。`,
            okText: "删除",
            okButtonProps: { danger: true },
            onOk: async () => {
              await api.deleteConversation(item.id);
              setConversations((current) =>
                current.filter((conversation) => conversation.id !== item.id),
              );
              if (activeId === item.id) {
                const nextConversation = conversations.find(
                  (conversation) => conversation.id !== item.id,
                );
                setActiveId(nextConversation?.id);
                navigateToConversation(
                  nextConversation?.workspace_id || activeWorkspaceId,
                  nextConversation?.id,
                  true,
                );
              }
              message.success("归档会话已删除");
            },
          });
        }}
      />
      <Layout className="center-layout">
        <div className="topbar">
          <Space>
            <Avatar>
              {currentUser.avatar ?? currentUser.name.slice(0, 1)}
            </Avatar>
            <div>
              <Text strong>{currentUser.name}</Text>
              <br />
              <Text type="secondary">
                {currentUser.role === "demo" ? "演示用户" : "成员"}
              </Text>
            </div>
          </Space>
          <Space>
            <Select
              style={{ width: 220 }}
              value={activeWorkspace?.id}
              placeholder="选择工作区"
              onChange={(value) => selectWorkspace(value)}
              options={workspaces.map((workspace) => ({
                label: workspace.name,
                value: workspace.id,
              }))}
            />
            <Button
              icon={<AppstoreOutlined />}
              onClick={() => openMainTab("workspace")}
              data-testid="workspace-panel"
            >
              工作区
            </Button>
            <BackgroundTasksButton
              tasks={visibleBackgroundTasks}
              conversations={conversations}
              activeConversationId={activeId}
              onOpenConversation={selectConversation}
              onCreate={async (prompt) => {
                await send(prompt);
                await loadBackgroundTasks().catch(() => undefined);
              }}
              onCancel={async (task) => {
                await api.cancelTask(task.id);
                if (task.conversation_id) {
                  await api
                    .cancelAssistantReply(task.conversation_id)
                    .catch(() => undefined);
                  setLocalRunningConversationIds((current) => {
                    const next = new Set(current);
                    if (task.conversation_id) next.delete(task.conversation_id);
                    return next;
                  });
                }
                await loadBackgroundTasks();
                message.info("后台任务已停止");
              }}
              onRefresh={loadBackgroundTasks}
            />
            <Button
              icon={<ToolOutlined />}
              onClick={() => openMainTab("settings")}
              data-testid="global-settings"
            >
              设置
            </Button>
            <Button
              icon={<RobotOutlined />}
              onClick={() => openMainTab("agents")}
              data-testid="agent-directory"
            >
              Agent 广场
            </Button>
            <Button onClick={onLogout}>退出</Button>
          </Space>
        </div>
        <ChatPanel
          user={currentUser}
          active={active}
          messages={messages}
          loading={loadingMessages}
          streamState={streamState}
          onSend={send}
          onRegenerate={regenerate}
          onOpenMembers={() => setMembersOpen(true)}
          onOpenSettings={() => setConversationSettingsOpen(true)}
          onUploadFile={uploadFile}
          onOpenPreview={openArtifactPreview}
          onStopStreaming={stopStreaming}
        />
      </Layout>
      {artifactPanelOpen && artifact && (
        <PreviewPanel
          artifact={artifact}
          deployment={deployment}
          files={files}
          knowledgeBases={knowledgeBases}
          onClose={() => setArtifactPanelOpen(false)}
          onSave={saveArtifact}
          onDeploy={deploy}
          onCreateKb={async (payload) => {
            const created = await api.createKnowledgeBase(payload);
            setKnowledgeBases((current) => [created, ...current]);
            message.success("知识库已创建");
          }}
          onImportText={async (kbId, payload) => {
            await api.importKnowledgeText(kbId, payload);
            setKnowledgeBases(await api.knowledgeBases());
            message.success("文档已索引");
          }}
          onRetrieve={async (kbId, query) => {
            const result = await api.retrieveKnowledge(kbId, query);
            return result.context;
          }}
        />
      )}
      <AgentDirectoryDrawer
        open={agentDrawerOpen}
        agents={agents}
        onClose={() => closeMainTab("agents")}
        onRefresh={loadAgents}
        onCreateAgent={(agent) => setAgents((current) => [agent, ...current])}
        onUpdateAgent={(agent) =>
          setAgents((current) =>
            current.map((item) => (item.id === agent.id ? agent : item)),
          )
        }
        onDeleteAgent={async (agent) => {
          await api.deleteAgent(agent.id);
          setAgents((current) =>
            current.filter((item) => item.id !== agent.id),
          );
        }}
        onTestAgent={async (agentId, text) =>
          (await api.testAgent(agentId, text)).response
        }
      />
      <MembersDrawer
        open={membersOpen}
        active={active}
        agents={agents}
        onClose={() => setMembersOpen(false)}
        onAddAgents={async (ids) => {
          if (!activeId) return;
          try {
            const updated = await api.addParticipants(activeId, ids);
            setConversations((current) =>
              current.map((item) => (item.id === activeId ? updated : item)),
            );
            message.success("成员已加入");
          } catch (error) {
            message.error(
              error instanceof Error ? error.message : "成员加入失败",
            );
          }
        }}
        onRemoveParticipant={async (participant) => {
          if (!activeId || !participant.id) return;
          const updated = await api.removeParticipant(activeId, participant.id);
          setConversations((current) =>
            current.map((item) => (item.id === activeId ? updated : item)),
          );
          message.success("成员已移除");
        }}
      />
      <ConversationSettingsDrawer
        open={conversationSettingsOpen}
        active={active}
        agents={agents}
        categoryOptions={conversationCategories}
        onClose={() => setConversationSettingsOpen(false)}
        onSaveConversation={patchConversation}
      />
      <CreateConversationModal
        open={createOpen.open}
        group={createOpen.group}
        agents={agents}
        categoryOptions={conversationCategories}
        onCancel={() => setCreateOpen({ open: false, group: false })}
        onCreate={createConversation}
      />
      <GlobalSettingsDrawer
        open={globalSettingsOpen}
        user={currentUser}
        onClose={() => closeMainTab("settings")}
        onUserUpdated={(nextUser) => {
          setCurrentUser(nextUser);
        }}
      />
      <PlatformControlDrawer
        open={workspacesOpen}
        workspaces={workspaces}
        activeConversation={active}
        onClose={() => closeMainTab("workspace")}
        onCreateWorkspace={async (payload) => {
          const created = await api.createWorkspace(payload);
          setWorkspaces((current) => [created, ...current]);
          setActiveWorkspaceId(created.id);
          navigateToConversation(created.id);
          message.success("工作区已创建");
        }}
        onCreateProject={async (workspaceId, payload) => {
          const project = await api.createProject(workspaceId, payload);
          setWorkspaces((current) =>
            current.map((workspace) =>
              workspace.id === workspaceId
                ? { ...workspace, project_count: workspace.project_count + 1 }
                : workspace,
            ),
          );
          message.success("项目已创建");
          return project;
        }}
        onLoadProjects={api.projects}
        onSaveProjectFile={async (projectId, payload) => {
          await api.saveProjectFile(projectId, payload);
          message.success("项目文件版本已保存");
        }}
      />
    </Layout>
  );
}
