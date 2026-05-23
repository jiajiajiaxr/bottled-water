import { create } from "zustand";

interface UIState {
  // 抽屉状态
  agentDirectoryOpen: boolean;
  workspaceDrawerOpen: boolean;
  settingsDrawerOpen: boolean;
  platformDrawerOpen: boolean;
  membersDrawerOpen: boolean;
  filesDrawerOpen: boolean;
  conversationSettingsOpen: boolean;
  previewPanelOpen: boolean;

  // 弹窗状态
  createConversationModalOpen: boolean;

  // actions
  setAgentDirectoryOpen: (open: boolean) => void;
  setWorkspaceDrawerOpen: (open: boolean) => void;
  setSettingsDrawerOpen: (open: boolean) => void;
  setPlatformDrawerOpen: (open: boolean) => void;
  setMembersDrawerOpen: (open: boolean) => void;
  setFilesDrawerOpen: (open: boolean) => void;
  setConversationSettingsOpen: (open: boolean) => void;
  setPreviewPanelOpen: (open: boolean) => void;
  setCreateConversationModalOpen: (open: boolean) => void;

  // 一键关闭所有抽屉
  closeAllDrawers: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  agentDirectoryOpen: false,
  workspaceDrawerOpen: false,
  settingsDrawerOpen: false,
  platformDrawerOpen: false,
  membersDrawerOpen: false,
  filesDrawerOpen: false,
  conversationSettingsOpen: false,
  previewPanelOpen: false,
  createConversationModalOpen: false,

  setAgentDirectoryOpen: (agentDirectoryOpen) => set({ agentDirectoryOpen }),
  setWorkspaceDrawerOpen: (workspaceDrawerOpen) => set({ workspaceDrawerOpen }),
  setSettingsDrawerOpen: (settingsDrawerOpen) => set({ settingsDrawerOpen }),
  setPlatformDrawerOpen: (platformDrawerOpen) => set({ platformDrawerOpen }),
  setMembersDrawerOpen: (membersDrawerOpen) => set({ membersDrawerOpen }),
  setFilesDrawerOpen: (filesDrawerOpen) => set({ filesDrawerOpen }),
  setConversationSettingsOpen: (conversationSettingsOpen) =>
    set({ conversationSettingsOpen }),
  setPreviewPanelOpen: (previewPanelOpen) => set({ previewPanelOpen }),
  setCreateConversationModalOpen: (createConversationModalOpen) =>
    set({ createConversationModalOpen }),

  closeAllDrawers: () =>
    set({
      agentDirectoryOpen: false,
      workspaceDrawerOpen: false,
      settingsDrawerOpen: false,
      platformDrawerOpen: false,
      membersDrawerOpen: false,
      filesDrawerOpen: false,
      conversationSettingsOpen: false,
      previewPanelOpen: false,
    }),
}));
