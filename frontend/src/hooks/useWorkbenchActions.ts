import { App as AntApp } from "antd";
import { api } from "@/api";
import {
  useConversationStore,
  useMessageStore,
  useArtifactStore,
  useUIStore,
} from "@/store";
import type {
  ChatMessage,
  Conversation,
  WorkspaceArtifact,
} from "@/types";

export function useWorkbenchActions(
  activeWorkspaceId: string | undefined,
  conversationCategories: string[],
  saveCategories: (categories: string[]) => void,
  navigateToConversation: (
    workspaceId?: string,
    conversationId?: string,
    replace?: boolean,
  ) => void,
) {
  const { message } = AntApp.useApp();
  const {
    activeId,
    setActiveId,
    updateConversations,
  } = useConversationStore();
  const { clearMessages } = useMessageStore();
  const {
    artifact,
    files,
    setArtifact,
    setFiles,
    setArtifactPanelOpen,
    setDeployment,
  } = useArtifactStore();
  const { setCreateOpen } = useUIStore();

  const patchConversation = async (
    item: Conversation,
    patch: Partial<Conversation>,
  ) => {
    const updated = await api.updateConversation(item.id, patch);
    const nextCategory =
      patch.folder || patch.category || updated.folder || updated.category;
    if (nextCategory)
      saveCategories([...conversationCategories, nextCategory]);
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
    masterEnabled: boolean;
    folder: string;
  }) => {
    const created = await api.createConversationWithAgents({
      chat_type: "group",
      title: payload.title,
      participant_agent_ids: payload.agentIds,
      master_enabled: payload.masterEnabled,
      folder: payload.folder,
      category: payload.folder,
      workspace_id: activeWorkspaceId,
    });
    saveCategories([...conversationCategories, payload.folder]);
    updateConversations((current) => [created, ...current]);
    setActiveId(created.id);
    navigateToConversation(
      created.workspace_id || activeWorkspaceId,
      created.id,
    );
    clearMessages();
    setCreateOpen({ open: false });
    message.success("会话已创建");
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

  return {
    patchConversation,
    createConversation,
    saveArtifact,
    deploy,
    uploadFile,
    openArtifactPreview,
  };
}
