import { request, requestFile } from "./client";
import type { WorkspaceFilePreview, WorkspaceFileTree } from "../types";

export async function workspaceFileTree(workspaceId: string): Promise<WorkspaceFileTree> {
  return await request<WorkspaceFileTree>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files/tree`,
  );
}

export async function previewWorkspaceFile(
  workspaceId: string,
  nodeId: string,
): Promise<WorkspaceFilePreview> {
  return await request<WorkspaceFilePreview>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files/preview?node_id=${encodeURIComponent(nodeId)}`,
  );
}

export async function downloadWorkspaceFile(workspaceId: string, nodeId: string) {
  return await requestFile(
    `/workspaces/${encodeURIComponent(workspaceId)}/files/download?node_id=${encodeURIComponent(nodeId)}`,
  );
}

export async function deleteWorkspaceFile(workspaceId: string, nodeId: string) {
  return await request<{ id: string; deleted: boolean }>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files?node_id=${encodeURIComponent(nodeId)}`,
    { method: "DELETE" },
  );
}
