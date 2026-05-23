import { request, requestFile } from "./client";
import type { WorkspaceArtifact } from "../types";

export async function artifact(
  conversationId: string,
): Promise<WorkspaceArtifact | undefined> {
  try {
    return await request<WorkspaceArtifact>(
      `/conversations/${conversationId}/artifact`,
    );
  } catch {
    return undefined;
  }
}

export async function artifactById(
  artifactId: string,
): Promise<WorkspaceArtifact | undefined> {
  try {
    return await request<WorkspaceArtifact>(`/artifacts/${artifactId}`);
  } catch {
    return undefined;
  }
}

export async function saveArtifact(artifact: WorkspaceArtifact): Promise<WorkspaceArtifact> {
  try {
    return await request<WorkspaceArtifact>(`/artifacts/${artifact.id}`, {
      method: "PUT",
      body: JSON.stringify({
        files: { "index.html": artifact.code },
        change_summary: "前端编辑保存",
      }),
    });
  } catch {
    return { ...artifact, updatedAt: new Date().toISOString() };
  }
}

export async function exportArtifact(
  artifactId: string,
  format: string,
): Promise<{
  previewUrl?: string;
  previewText?: string;
  contentType: string;
  filename?: string;
}> {
  return await requestFile(
    `/artifacts/${artifactId}/export?format=${encodeURIComponent(format)}`,
  );
}
