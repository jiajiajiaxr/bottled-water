import {
  App as AntApp,
  Button,
  Layout,
  Modal,
  Segmented,
  Select,
  Space,
} from "antd";
import {
  AppstoreOutlined,
  BranchesOutlined,
  CommentOutlined,
  RobotOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { api } from "@/api";
import { ConversationSidebar } from "@/features/chat/components/ConversationSidebar";
import type {
  Conversation,
  User,
  Workspace,
} from "@/types";

export interface WorkbenchLayoutProps {
  // User
  currentUser: User;
  onLogout: () => void;

  // Workspaces
  workspaces: Workspace[];
  activeWorkspace: Workspace | undefined;
  activeWorkspaceId: string | undefined;
  selectWorkspace: (workspaceId?: string, replace?: boolean) => void;
  openMainTab: (tab: "agents" | "workspace" | "settings") => void;

  // Conversations
  conversations: Conversation[];
  activeId: string | undefined;
  conversationCategories: string[];
  selectConversation: (conversationId?: string, replace?: boolean) => void;
  setCreateOpen: (value: { open: boolean }) => void;
  addConversationCategory: (name: string) => void;
  patchConversation: (
    item: Conversation,
    patch: Partial<Conversation>,
  ) => Promise<void>;
  updateConversations: (
    updater: (current: Conversation[]) => Conversation[],
  ) => void;
  setActiveId: (id: string | undefined) => void;
  navigateToConversation: (
    workspaceId?: string,
    conversationId?: string,
    replace?: boolean,
  ) => void;

  runningConversationIds: Set<string>;

  // Main content
  routeTab: string;
  scheduleMode: "chat" | "workflow";
  onScheduleModeChange: (mode: "chat" | "workflow") => void;
  children: React.ReactNode;
}

export function WorkbenchLayout(props: WorkbenchLayoutProps) {
  const { message } = AntApp.useApp();

  const {
    currentUser,
    onLogout,
    workspaces,
    activeWorkspace,
    activeWorkspaceId,
    selectWorkspace,
    openMainTab,
    conversations,
    activeId,
    conversationCategories,
    selectConversation,
    setCreateOpen,
    addConversationCategory,
    patchConversation,
    updateConversations,
    setActiveId,
    navigateToConversation,
    runningConversationIds,
    routeTab,
    scheduleMode,
    onScheduleModeChange,
    children,
  } = props;

  return (
    <Layout className="workbench">
      <ConversationSidebar
        currentUser={currentUser}
        conversations={conversations}
        activeId={activeId}
        runningConversationIds={runningConversationIds}
        categoryOptions={conversationCategories}
        onSelect={selectConversation}
        onCreate={() => setCreateOpen({ open: true })}
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
              updateConversations((current) =>
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
          </Space>
          <Space>
            {routeTab === "chat" && (
              <Segmented
                value={scheduleMode}
                onChange={(value) => onScheduleModeChange(value as "chat" | "workflow")}
                options={[
                  { label: <><CommentOutlined /> 一般</>, value: "chat" },
                  { label: <><BranchesOutlined /> 工作流</>, value: "workflow" },
                ]}
              />
            )}
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
        {children}
      </Layout>
    </Layout>
  );
}
