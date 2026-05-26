import { useEffect, useMemo, useState } from "react";
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
import type { User } from "../../types";
import {
  useConversationCategories,
  useBackgroundTaskPolling,
  useMessageOperations,
  useWorkbenchActions,
} from "../../hooks";
import { isTaskRunning } from "../../lib/message";

export function Workbench({
  user,
  onLogout,
  routeWorkspaceId,
  routeConversationId,
  routeTab = "chat",
  onRouteChange,
  onRouteTabChange,
  onOpenWorkflowPage,
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
  onOpenWorkflowPage: (workspaceId: string, conversationId: string) => void;
}) {
  const [currentUser, setCurrentUser] = useState(user);
  const {
    messages,
    setMessages,
    streamState,
    localRunningConversationIds,
    updateLocalRunningConversationIds,
  } = useMessageStore();
  const {
    workspaces,
    setWorkspaces,
    activeWorkspaceId,
    setActiveWorkspaceId,
    addWorkspace,
    updateWorkspace,
  } = useWorkspaceStore();
  const {
    conversations,
    setConversations,
    activeId,
    setActiveId,
    loadingMessages,
    setLoadingMessages,
    updateConversations,
  } = useConversationStore();
  const { conversationCategories, addCategory, saveCategories } =
    useConversationCategories(activeWorkspaceId, conversations);
  const {
    artifact,
    setArtifact,
    deployment,
    files,
    setFiles,
    knowledgeBases,
    setKnowledgeBases,
  } = useArtifactStore();
  const { agents, setAgents, addAgent, updateAgent, removeAgent } =
    useAgentStore();
  const { backgroundTasks } = useTaskStore();
  const { loadBackgroundTasks } = useBackgroundTaskPolling();
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
  const { send, regenerate, stopStreaming } = useMessageOperations(
    currentUser.name,
  );

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

  const openWorkflowPage = () => {
    if (!active?.id || active.chat_type !== "group") return;
    const workspaceId = active.workspace_id || activeWorkspaceId || activeWorkspace?.id;
    if (!workspaceId) return;
    onOpenWorkflowPage(workspaceId, active.id);
  };

  const closeMainTab = (tab: "agents" | "workspace" | "settings") => {
    if (tab === "agents") setAgentDrawerOpen(false);
    if (tab === "workspace") setWorkspacesOpen(false);
    if (tab === "settings") setGlobalSettingsOpen(false);
    if (routeTab === tab) onRouteTabChange("chat");
  };

  const loadAgents = async () => setAgents(await api.agents());
  const {
    patchConversation,
    createConversation,
    saveArtifact,
    deploy,
    uploadFile,
    openArtifactPreview,
  } = useWorkbenchActions(
    activeWorkspaceId,
    conversationCategories,
    saveCategories,
    navigateToConversation,
  );

  useEffect(() => {
    setCurrentUser(user);
  }, [user]);

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
        addConversationCategory={addCategory}
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
        openWorkflowPage={openWorkflowPage}
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
        onOpenWorkflow={openWorkflowPage}
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
