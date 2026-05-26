import { App as AntApp } from "antd";
import { api } from "@/api";
import { CreateConversationModal } from "@/features/chat/components/CreateConversationModal";
import { MembersDrawer } from "@/features/chat/components/drawers/MembersDrawer";
import { ConversationSettingsDrawer } from "@/features/chat/components/drawers/ConversationSettingsDrawer";
import { AgentDirectoryDrawer } from "@/features/agents/components/AgentDirectoryDrawer";
import { GlobalSettingsDrawer } from "@/features/settings/components/GlobalSettingsDrawer";
import { PlatformControlDrawer } from "@/features/platform/components/PlatformControlDrawer";
import type { Agent, Conversation, Project, User, Workspace } from "@/types";

export interface WorkbenchDrawersProps {
  // AgentDirectoryDrawer
  agentDrawerOpen: boolean;
  agents: Agent[];
  onCloseAgentDrawer: () => void;
  onRefreshAgents: () => void;
  onCreateAgent: (agent: Agent) => void;
  onUpdateAgent: (agent: Agent) => void;
  onDeleteAgent: (agent: Agent) => Promise<void>;
  onTestAgent: (agentId: string, text: string) => Promise<string>;

  // MembersDrawer
  membersOpen: boolean;
  activeConversation: Conversation | undefined;
  activeConversationId: string | undefined;
  onCloseMembers: () => void;
  onUpdateConversations: (
    updater: (current: Conversation[]) => Conversation[],
  ) => void;

  // ConversationSettingsDrawer
  conversationSettingsOpen: boolean;
  onCloseConversationSettings: () => void;
  conversationCategories: string[];
  onPatchConversation: (
    item: Conversation,
    patch: Partial<Conversation>,
  ) => Promise<void>;

  // CreateConversationModal
  createOpen: { open: boolean; group: boolean };
  onCancelCreate: () => void;
  onCreateConversation: (payload: {
    title?: string;
    agentIds: string[];
    group: boolean;
    masterEnabled: boolean;
    folder: string;
  }) => Promise<void>;

  // GlobalSettingsDrawer
  globalSettingsOpen: boolean;
  currentUser: User;
  onCloseGlobalSettings: () => void;
  onUserUpdated: (user: User) => void;

  // PlatformControlDrawer
  workspacesOpen: boolean;
  workspaces: Workspace[];
  onCloseWorkspaces: () => void;
  onLoadProjects: (workspaceId: string) => Promise<Project[]>;
  onSetActiveWorkspaceId: (id: string) => void;
  onNavigateToConversation: (workspaceId?: string, conversationId?: string, replace?: boolean) => void;
  onAddWorkspace: (workspace: Workspace) => void;
  onUpdateWorkspace: (id: string, patch: Partial<Workspace>) => void;
}

export function WorkbenchDrawers(props: WorkbenchDrawersProps) {
  const { message } = AntApp.useApp();

  const {
    agentDrawerOpen,
    agents,
    onCloseAgentDrawer,
    onRefreshAgents,
    onCreateAgent,
    onUpdateAgent,
    onDeleteAgent,
    onTestAgent,

    membersOpen,
    activeConversation,
    activeConversationId,
    onCloseMembers,
    onUpdateConversations,

    conversationSettingsOpen,
    onCloseConversationSettings,
    conversationCategories,
    onPatchConversation,

    createOpen,
    onCancelCreate,
    onCreateConversation,

    globalSettingsOpen,
    currentUser,
    onCloseGlobalSettings,
    onUserUpdated,

    workspacesOpen,
    workspaces,
    onCloseWorkspaces,
    onLoadProjects,
    onSetActiveWorkspaceId,
    onNavigateToConversation,
    onAddWorkspace,
    onUpdateWorkspace,
  } = props;

  return (
    <>
      <AgentDirectoryDrawer
        open={agentDrawerOpen}
        agents={agents}
        onClose={onCloseAgentDrawer}
        onRefresh={onRefreshAgents}
        onCreateAgent={onCreateAgent}
        onUpdateAgent={(agent) => onUpdateAgent(agent)}
        onDeleteAgent={onDeleteAgent}
        onTestAgent={onTestAgent}
      />
      <MembersDrawer
        open={membersOpen}
        active={activeConversation}
        agents={agents}
        onClose={onCloseMembers}
        onAddAgents={async (ids) => {
          if (!activeConversationId) return;
          try {
            const updated = await api.addParticipants(activeConversationId, ids);
            onUpdateConversations((current) =>
              current.map((item) => (item.id === activeConversationId ? updated : item)),
            );
            message.success("成员已加入");
          } catch (error) {
            message.error(
              error instanceof Error ? error.message : "成员加入失败",
            );
          }
        }}
        onRemoveParticipant={async (participant) => {
          if (!activeConversationId || !participant.id) return;
          const updated = await api.removeParticipant(activeConversationId, participant.id);
          onUpdateConversations((current) =>
            current.map((item) => (item.id === activeConversationId ? updated : item)),
          );
          message.success("成员已移除");
        }}
      />
      <ConversationSettingsDrawer
        open={conversationSettingsOpen}
        active={activeConversation}
        agents={agents}
        categoryOptions={conversationCategories}
        onClose={onCloseConversationSettings}
        onSaveConversation={onPatchConversation}
      />
      <CreateConversationModal
        open={createOpen.open}
        group={createOpen.group}
        agents={agents}
        categoryOptions={conversationCategories}
        onCancel={onCancelCreate}
        onCreate={onCreateConversation}
      />
      <GlobalSettingsDrawer
        open={globalSettingsOpen}
        user={currentUser}
        onClose={onCloseGlobalSettings}
        onUserUpdated={(nextUser) => {
          onUserUpdated(nextUser);
        }}
      />
      <PlatformControlDrawer
        open={workspacesOpen}
        workspaces={workspaces}
        activeConversation={activeConversation}
        onClose={onCloseWorkspaces}
        onCreateWorkspace={async (payload) => {
          const created = await api.createWorkspace(payload);
          onAddWorkspace(created);
          onSetActiveWorkspaceId(created.id);
          onNavigateToConversation(created.id);
          message.success("工作区已创建");
        }}
        onCreateProject={async (workspaceId, payload) => {
          const project = await api.createProject(workspaceId, payload);
          const workspace = workspaces.find((w) => w.id === workspaceId);
          if (workspace) {
            onUpdateWorkspace(workspaceId, {
              project_count: workspace.project_count + 1,
            });
          }
          message.success("项目已创建");
          return project;
        }}
        onLoadProjects={onLoadProjects}
        onSaveProjectFile={async (projectId, payload) => {
          await api.saveProjectFile(projectId, payload);
          message.success("项目文件版本已保存");
        }}
      />
    </>
  );
}
