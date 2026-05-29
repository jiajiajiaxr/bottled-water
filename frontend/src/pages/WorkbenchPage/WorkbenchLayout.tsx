import {
  useCallback,
  useState,
} from "react";
import type { PointerEvent } from "react";
import { useNavigate } from "react-router-dom";
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
  BookOutlined,
  RobotOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import { api } from "../../api";
import { BackgroundTasksButton } from "./BackgroundTasksButton";
import { ConversationSidebar } from "../../features/chat/components/ConversationSidebar";
import { ChatPanel } from "../../features/chat/components/ChatPanel";
import { PreviewPanel } from "../../features/preview/components/PreviewPanel";
import { WorkflowStudioContent } from "../../features/workflow/WorkflowStudioContent";
import type {
  AgentTask,
  ChatMessage,
  Conversation,
  Deployment,
  KnowledgeBase,
  UploadedFile,
  User,
  Workspace,
  WorkspaceArtifact,
} from "../../types";
import type { StreamState } from "../../store/useMessageStore";

const { Text } = Typography;
const PREVIEW_MIN_WIDTH = 360;
const PREVIEW_DEFAULT_WIDTH = 680;

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
  active: Conversation | undefined;
  conversationCategories: string[];
  selectConversation: (conversationId?: string, replace?: boolean) => void;
  setCreateOpen: (value: { open: boolean; group: boolean }) => void;
  addConversationCategory: (name: string) => void;
  patchConversation: (item: Conversation, patch: Partial<Conversation>) => Promise<void>;
  updateConversations: (
    updater: (current: Conversation[]) => Conversation[],
  ) => void;
  setActiveId: (id: string | undefined) => void;
  navigateToConversation: (
    workspaceId?: string,
    conversationId?: string,
    replace?: boolean,
  ) => void;

  // Messages
  messages: ChatMessage[];
  loadingMessages: boolean;
  streamState: StreamState;
  send: (text: string, quoted?: ChatMessage, attachments?: UploadedFile[], thinkingEnabled?: boolean) => Promise<void>;
  regenerate: (source: ChatMessage) => void;
  stopStreaming: () => void;

  // UI state setters
  setMembersOpen: (open: boolean) => void;
  setConversationSettingsOpen: (open: boolean) => void;
  openWorkflowPage: () => void;
  closeWorkflowPage: () => void;
  workflowMode: boolean;

  // File upload
  uploadFile: (file: File) => Promise<UploadedFile>;

  // Artifact / Preview
  artifactPanelOpen: boolean;
  artifact: WorkspaceArtifact | undefined;
  deployment: Deployment | undefined;
  files: UploadedFile[];
  knowledgeBases: KnowledgeBase[];
  setArtifactPanelOpen: (open: boolean) => void;
  saveArtifact: (artifact: WorkspaceArtifact) => Promise<void>;
  deploy: () => Promise<void>;
  setKnowledgeBases: (kbs: KnowledgeBase[]) => void;
  openArtifactPreview: (source?: ChatMessage) => Promise<void>;

  // Background tasks
  visibleBackgroundTasks: AgentTask[];
  loadBackgroundTasks: () => Promise<void>;
  updateLocalRunningConversationIds: (
    updater: (current: Set<string>) => Set<string>,
  ) => void;
  runningConversationIds: Set<string>;
}

export function WorkbenchLayout(props: WorkbenchLayoutProps) {
  const { message } = AntApp.useApp();
  const navigate = useNavigate();
  const [previewWidth, setPreviewWidth] = useState(() => {
    const value = Number(window.localStorage.getItem("agenthub_preview_width"));
    return Number.isFinite(value) && value >= PREVIEW_MIN_WIDTH
      ? value
      : PREVIEW_DEFAULT_WIDTH;
  });

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
    active,
    conversationCategories,
    selectConversation,
    setCreateOpen,
    addConversationCategory,
    patchConversation,
    updateConversations,
    setActiveId,
    navigateToConversation,
    messages,
    loadingMessages,
    streamState,
    send,
    regenerate,
    stopStreaming,
    setMembersOpen,
    setConversationSettingsOpen,
    openWorkflowPage,
    closeWorkflowPage,
    workflowMode,
    uploadFile,
    artifactPanelOpen,
    artifact,
    deployment,
    files,
    knowledgeBases,
    setArtifactPanelOpen,
    saveArtifact,
    deploy,
    setKnowledgeBases,
    openArtifactPreview,
    visibleBackgroundTasks,
    loadBackgroundTasks,
    updateLocalRunningConversationIds,
    runningConversationIds,
  } = props;
  const workflowWorkspaceId = active?.workspace_id || activeWorkspaceId;
  const startPreviewResize = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      const clampWidth = (width: number) => {
        const maxWidth = Math.max(
          PREVIEW_MIN_WIDTH,
          Math.floor(window.innerWidth * 0.78),
        );
        return Math.min(maxWidth, Math.max(PREVIEW_MIN_WIDTH, width));
      };
      let latestWidth = clampWidth(window.innerWidth - event.clientX);
      const handleMove = (moveEvent: globalThis.PointerEvent) => {
        const nextWidth = clampWidth(window.innerWidth - moveEvent.clientX);
        latestWidth = nextWidth;
        setPreviewWidth(nextWidth);
      };
      const handleUp = () => {
        window.localStorage.setItem("agenthub_preview_width", String(latestWidth));
        window.removeEventListener("pointermove", handleMove);
        window.removeEventListener("pointerup", handleUp);
        document.body.classList.remove("is-resizing-preview");
      };
      document.body.classList.add("is-resizing-preview");
      window.addEventListener("pointermove", handleMove);
      window.addEventListener("pointerup", handleUp, { once: true });
    },
    [],
  );

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
                  updateLocalRunningConversationIds((current) => {
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
              icon={<BookOutlined />}
              onClick={() => navigate("/docs")}
              data-testid="docs-link"
            >
              文档
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
          onOpenWorkflow={openWorkflowPage}
          workflowMode={workflowMode}
          workflowContent={
            workflowMode && activeId && workflowWorkspaceId ? (
              <WorkflowStudioContent
                workspaceId={workflowWorkspaceId}
                conversationId={activeId}
                embedded
                onBack={closeWorkflowPage}
                onError={(value) => message.error(value)}
                onSuccess={(value) => message.success(value)}
              />
            ) : undefined
          }
          onUploadFile={uploadFile}
          onOpenPreview={openArtifactPreview}
          onStopStreaming={stopStreaming}
        />
      </Layout>
      {artifactPanelOpen && artifact && (
        <PreviewPanel
          artifact={artifact}
          width={previewWidth}
          onResizeStart={startPreviewResize}
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
    </Layout>
  );
}
