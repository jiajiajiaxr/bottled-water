import { get, request, requestFile } from "./client";
import type { WorkspaceArtifact } from "@/types";

export async function artifact(
  conversationId: string,
): Promise<WorkspaceArtifact | undefined> {
  return await get<WorkspaceArtifact>(`/conversations/${conversationId}/artifact`);
}

export async function artifactById(
  artifactId: string,
): Promise<WorkspaceArtifact | undefined> {
  return await get<WorkspaceArtifact>(`/artifacts/${artifactId}`);
}

export async function saveArtifact(artifact: WorkspaceArtifact): Promise<WorkspaceArtifact> {
  return await request<WorkspaceArtifact>(`/artifacts/${artifact.id}`, {
    method: "PUT",
    body: JSON.stringify({
      files: { "index.html": artifact.code },
      change_summary: "前端编辑保存",
    }),
  });
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

export async function previewArtifactPdf(
  artifactId: string,
): Promise<{
  previewUrl?: string;
  previewText?: string;
  contentType: string;
  filename?: string;
}> {
  return await requestFile(`/artifacts/${artifactId}/preview-pdf`);
}
