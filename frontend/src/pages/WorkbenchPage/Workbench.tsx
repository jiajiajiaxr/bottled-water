import { useEffect, useMemo, useState } from "react";
import { App as AntApp } from "antd";
import { api } from "@/api";
import {
  useUIStore,
  useAgentStore,
  useWorkspaceStore,
  useTaskStore,
  useArtifactStore,
  useConversationStore,
  useMessageStore,
} from "@/store";
import { WorkbenchLayout } from "./WorkbenchLayout";
import { WorkbenchDrawers } from "./WorkbenchDrawers";
import { AgentDirectoryDrawer } from "@/features/agents/components/AgentDirectoryDrawer";
import { GlobalSettingsDrawer } from "@/features/settings/components/GlobalSettingsDrawer";
import { PlatformControlDrawer } from "@/features/platform/components/PlatformControlDrawer";
import { ChatPanel } from "@/features/chat/components/ChatPanel";
import { PreviewPanel } from "@/features/preview/components/PreviewPanel";
import { WorkflowStudioContent } from "@/features/workflow/WorkflowStudioContent";
import type { User } from "@/types";
import {
  useConversationCategories,
  useBackgroundTaskPolling,
  useWorkbenchActions,
} from "@/hooks";
import { isTaskRunning } from "@/lib/message";

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
  const { message } = AntApp.useApp();
  const [currentUser, setCurrentUser] = useState(user);
  const { setMessages, clearMessages } = useMessageStore();
  const {
    localRunningConversationIds,
  } = useConversationStore();
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
    conversationSettingsOpen,
    membersOpen,
    createOpen,
    artifactPanelOpen,
    scheduleMode,
    setAgentDrawerOpen,
    setWorkspacesOpen,
    setGlobalSettingsOpen,
    setConversationSettingsOpen,
    setMembersOpen,
    setCreateOpen,
    setArtifactPanelOpen,
    setScheduleMode,
  } = useUIStore();
  const active = conversations.find((item) => item.id === activeId);
  const activeWorkspace =
    workspaces.find((workspace) => workspace.id === activeWorkspaceId) ??
    workspaces[0];
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
    clearMessages();
    setArtifact(undefined);
    setArtifactPanelOpen(false);
    api.conversations(activeWorkspaceId).then((items) => {
      if (!cancelled) setConversations(items);
    });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, workspaces.length, setArtifactPanelOpen, setArtifact, setActiveId, setConversations, clearMessages]);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    const scopedConversations = conversations.filter(
      (item) => (item.workspace_id || undefined) === activeWorkspaceId,
    );
    if (!scopedConversations.length) {
      setActiveId(undefined);
      // 不在此处清除 URL，等 conversations 加载完成后再恢复
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
      api.artifact(activeId).catch(() => undefined),
      api.files(activeId).catch(() => []),
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
        conversationCategories={conversationCategories}
        selectConversation={selectConversation}
        setCreateOpen={setCreateOpen}
        addConversationCategory={addCategory}
        patchConversation={patchConversation}
        updateConversations={updateConversations}
        setActiveId={setActiveId}
        navigateToConversation={navigateToConversation}
        runningConversationIds={runningConversationIds}
        routeTab={routeTab}
        scheduleMode={scheduleMode}
        onScheduleModeChange={setScheduleMode}
      >
        {routeTab === "chat" ? (
          scheduleMode === "workflow" && active ? (
            <WorkflowStudioContent
              workspaceId={activeWorkspaceId || ""}
              conversationId={active.id}
              embedded
              onError={(value) => message.error(value)}
              onSuccess={(value) => message.success(value)}
            />
          ) : (
            <>
              <ChatPanel active={active} loading={loadingMessages} userName={currentUser.name} />
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
                    setKnowledgeBases([created, ...knowledgeBases]);
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
            </>
          )
        ) : routeTab === "agents" ? (
          <AgentDirectoryDrawer
            asPage
            agents={agents}
            onClose={() => closeMainTab("agents")}
            onRefresh={loadAgents}
            onCreateAgent={addAgent}
            onUpdateAgent={(agent) => updateAgent(agent.id, agent)}
            onDeleteAgent={async (agent) => {
              await api.deleteAgent(agent.id);
              removeAgent(agent.id);
            }}
            onTestAgent={async (agentId, text) =>
              (await api.testAgent(agentId, text)).response
            }
          />
        ) : routeTab === "settings" ? (
          <GlobalSettingsDrawer
            asPage
            user={currentUser}
            onClose={() => closeMainTab("settings")}
            onUserUpdated={(nextUser) => setCurrentUser(nextUser)}
          />
        ) : routeTab === "workspace" ? (
          <PlatformControlDrawer
            asPage
            workspaces={workspaces}
            activeConversation={active}
            onClose={() => closeMainTab("workspace")}
            onCreateWorkspace={async (payload) => {
              const created = await api.createWorkspace(payload);
              addWorkspace(created);
              setActiveWorkspaceId(created.id);
              navigateToConversation(created.id);
              message.success("工作区已创建");
            }}
            onCreateProject={async (workspaceId, payload) => {
              const project = await api.createProject(workspaceId, payload);
              const workspace = workspaces.find((w) => w.id === workspaceId);
              if (workspace) {
                updateWorkspace(workspaceId, {
                  project_count: workspace.project_count + 1,
                });
              }
              message.success("项目已创建");
              return project;
            }}
            onLoadProjects={api.projects}
            onSaveProjectFile={async (projectId, payload) => {
              await api.saveProjectFile(projectId, payload);
              message.success("项目文件版本已保存");
            }}
          />
        ) : null}
      </WorkbenchLayout>
      <WorkbenchDrawers
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
        onCancelCreate={() => setCreateOpen({ open: false })}
        onCreateConversation={createConversation}
        agents={agents}
      />
    </>
  );
}
