import { create } from "zustand";

interface CreateModalState {
  open: boolean;
}

interface UIState {
  agentDrawerOpen: boolean;
  workspacesOpen: boolean;
  globalSettingsOpen: boolean;
  platformDrawerOpen: boolean;
  membersOpen: boolean;
  conversationSettingsOpen: boolean;
  artifactPanelOpen: boolean;
  createOpen: CreateModalState;
  scheduleMode: "chat" | "workflow";

  setAgentDrawerOpen: (open: boolean) => void;
  setScheduleMode: (mode: "chat" | "workflow") => void;
  setWorkspacesOpen: (open: boolean) => void;
  setGlobalSettingsOpen: (open: boolean) => void;
  setPlatformDrawerOpen: (open: boolean) => void;
  setMembersOpen: (open: boolean) => void;
  setConversationSettingsOpen: (open: boolean) => void;
  setArtifactPanelOpen: (open: boolean) => void;
  setCreateOpen: (state: CreateModalState) => void;

  closeAllDrawers: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  agentDrawerOpen: false,
  workspacesOpen: false,
  globalSettingsOpen: false,
  platformDrawerOpen: false,
  membersOpen: false,
  conversationSettingsOpen: false,
  artifactPanelOpen: false,
  createOpen: { open: false },
  scheduleMode: "chat",

  setAgentDrawerOpen: (agentDrawerOpen) => set({ agentDrawerOpen }),
  setScheduleMode: (scheduleMode) => set({ scheduleMode }),
  setWorkspacesOpen: (workspacesOpen) => set({ workspacesOpen }),
  setGlobalSettingsOpen: (globalSettingsOpen) => set({ globalSettingsOpen }),
  setPlatformDrawerOpen: (platformDrawerOpen) => set({ platformDrawerOpen }),
  setMembersOpen: (membersOpen) => set({ membersOpen }),
  setConversationSettingsOpen: (conversationSettingsOpen) =>
    set({ conversationSettingsOpen }),
  setArtifactPanelOpen: (artifactPanelOpen) => set({ artifactPanelOpen }),
  setCreateOpen: (createOpen) => set({ createOpen }),

  closeAllDrawers: () =>
    set({
      agentDrawerOpen: false,
      workspacesOpen: false,
      globalSettingsOpen: false,
      platformDrawerOpen: false,
      membersOpen: false,
      conversationSettingsOpen: false,
      artifactPanelOpen: false,
    }),
}));
