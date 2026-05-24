import { create } from "zustand";
import type {
  Deployment,
  KnowledgeBase,
  UploadedFile,
  WorkspaceArtifact,
} from "../types";

interface ArtifactState {
  artifact: WorkspaceArtifact | undefined;
  artifactPanelOpen: boolean;
  deployment: Deployment | undefined;
  files: UploadedFile[];
  knowledgeBases: KnowledgeBase[];
  setArtifact: (artifact: WorkspaceArtifact | undefined) => void;
  setArtifactPanelOpen: (open: boolean) => void;
  setDeployment: (deployment: Deployment | undefined) => void;
  setFiles: (files: UploadedFile[]) => void;
  setKnowledgeBases: (kbs: KnowledgeBase[]) => void;
}

export const useArtifactStore = create<ArtifactState>((set) => ({
  artifact: undefined,
  artifactPanelOpen: false,
  deployment: undefined,
  files: [],
  knowledgeBases: [],
  setArtifact: (artifact) => set({ artifact }),
  setArtifactPanelOpen: (artifactPanelOpen) => set({ artifactPanelOpen }),
  setDeployment: (deployment) => set({ deployment }),
  setFiles: (files) => set({ files }),
  setKnowledgeBases: (knowledgeBases) => set({ knowledgeBases }),
}));
