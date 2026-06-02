import { create } from "zustand";
import type { Agent } from "@/types";

interface AgentState {
  agents: Agent[];
  isLoading: boolean;
  setAgents: (agents: Agent[]) => void;
  updateAgent: (id: string, patch: Partial<Agent>) => void;
  addAgent: (agent: Agent) => void;
  removeAgent: (id: string) => void;
  setLoading: (loading: boolean) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  agents: [],
  isLoading: false,
  setAgents: (agents) => set({ agents }),
  updateAgent: (id, patch) =>
    set((state) => ({
      agents: state.agents.map((a) => (a.id === id ? { ...a, ...patch } : a)),
    })),
  addAgent: (agent) =>
    set((state) => ({
      agents: [...state.agents, agent],
    })),
  removeAgent: (id) =>
    set((state) => ({
      agents: state.agents.filter((a) => a.id !== id),
    })),
  setLoading: (isLoading) => set({ isLoading }),
}));
