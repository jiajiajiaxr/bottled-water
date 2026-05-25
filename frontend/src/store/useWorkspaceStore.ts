import { create } from "zustand";
import type { Workspace } from "../types";

interface WorkspaceState {
  workspaces: Workspace[];
  currentWorkspaceId: string | null;
  activeWorkspaceId: string | undefined;
  isLoading: boolean;
  setWorkspaces: (workspaces: Workspace[]) => void;
  setCurrentWorkspaceId: (id: string | null) => void;
  setActiveWorkspaceId: (id: string | undefined) => void;
  addWorkspace: (workspace: Workspace) => void;
  updateWorkspace: (id: string, patch: Partial<Workspace>) => void;
  setLoading: (loading: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  workspaces: [],
  currentWorkspaceId: null,
  activeWorkspaceId: undefined,
  isLoading: false,
  setWorkspaces: (workspaces) => set({ workspaces }),
  setCurrentWorkspaceId: (id) => set({ currentWorkspaceId: id }),
  setActiveWorkspaceId: (activeWorkspaceId) => set({ activeWorkspaceId }),
  addWorkspace: (workspace) =>
    set((state) => ({
      workspaces: [...state.workspaces, workspace],
    })),
  updateWorkspace: (id, patch) =>
    set((state) => ({
      workspaces: state.workspaces.map((w) =>
        w.id === id ? { ...w, ...patch } : w,
      ),
    })),
  setLoading: (isLoading) => set({ isLoading }),
}));
