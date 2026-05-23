import { create } from "zustand";
import type { Workspace } from "../types";

interface WorkspaceState {
  workspaces: Workspace[];
  currentWorkspaceId: string | null;
  isLoading: boolean;
  setWorkspaces: (workspaces: Workspace[]) => void;
  setCurrentWorkspaceId: (id: string | null) => void;
  addWorkspace: (workspace: Workspace) => void;
  updateWorkspace: (id: string, patch: Partial<Workspace>) => void;
  setLoading: (loading: boolean) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  workspaces: [],
  currentWorkspaceId: null,
  isLoading: false,
  setWorkspaces: (workspaces) => set({ workspaces }),
  setCurrentWorkspaceId: (id) => set({ currentWorkspaceId: id }),
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
