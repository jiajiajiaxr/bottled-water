import { request, requestFile } from "./client";
import type { WorkspaceArtifact } from "../types";

function normalizeArtifact(value: WorkspaceArtifact): WorkspaceArtifact {
  return {
    ...value,
    conversationId:
      value.conversationId ??
      (value as WorkspaceArtifact & { conversation_id?: string })
        .conversation_id ??
      "",
    previewUrl: value.previewUrl ?? value.preview_url,
    updatedAt:
      value.updatedAt ??
      (value as WorkspaceArtifact & { updated_at?: string }).updated_at ??
      new Date().toISOString(),
  };
}

export async function artifact(
  conversationId: string,
): Promise<WorkspaceArtifact | undefined> {
  try {
    return normalizeArtifact(await request<WorkspaceArtifact>(
      `/conversations/${conversationId}/artifact`,
    ));
  } catch {
    return undefined;
  }
}

export async function artifactById(
  artifactId: string,
): Promise<WorkspaceArtifact | undefined> {
  try {
    return normalizeArtifact(await request<WorkspaceArtifact>(`/artifacts/${artifactId}`));
  } catch {
    return undefined;
  }
}

export async function saveArtifact(artifact: WorkspaceArtifact): Promise<WorkspaceArtifact> {
  try {
    return normalizeArtifact(await request<WorkspaceArtifact>(`/artifacts/${artifact.id}`, {
      method: "PUT",
      body: JSON.stringify({
        files: { "index.html": artifact.code },
        change_summary: "前端编辑保存",
      }),
    }));
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
