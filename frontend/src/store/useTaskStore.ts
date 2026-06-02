import { create } from "zustand";
import type { AgentTask } from "@/types";

interface TaskState {
  backgroundTasks: AgentTask[];
  setBackgroundTasks: (tasks: AgentTask[]) => void;
  addBackgroundTask: (task: AgentTask) => void;
  updateBackgroundTask: (id: string, patch: Partial<AgentTask>) => void;
  removeBackgroundTask: (id: string) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  backgroundTasks: [],
  setBackgroundTasks: (backgroundTasks) => set({ backgroundTasks }),
  addBackgroundTask: (task) =>
    set((state) => ({
      backgroundTasks: [task, ...state.backgroundTasks],
    })),
  updateBackgroundTask: (id, patch) =>
    set((state) => ({
      backgroundTasks: state.backgroundTasks.map((t) =>
        t.id === id ? { ...t, ...patch } : t,
      ),
    })),
  removeBackgroundTask: (id) =>
    set((state) => ({
      backgroundTasks: state.backgroundTasks.filter((t) => t.id !== id),
    })),
}));
