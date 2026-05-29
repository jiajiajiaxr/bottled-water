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

export async function renameWorkspaceFile(
  workspaceId: string,
  nodeId: string,
  name: string,
) {
  return await request<{ id: string; name: string; display_name?: string }>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files?node_id=${encodeURIComponent(nodeId)}`,
    { method: "PATCH", body: JSON.stringify({ name }) },
  );
}

export async function createWorkspaceFolder(
  workspaceId: string,
  parentPath: string,
  name: string,
) {
  return await request<{ path: string; name: string; display_name?: string }>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files/folders`,
    { method: "POST", body: JSON.stringify({ parent_path: parentPath, name }) },
  );
}

export async function moveWorkspaceFiles(
  workspaceId: string,
  nodeIds: string[],
  targetPath: string,
) {
  return await request<{ moved: Array<{ id: string; path: string }> }>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files/move`,
    { method: "POST", body: JSON.stringify({ node_ids: nodeIds, target_path: targetPath }) },
  );
}

export async function favoriteWorkspaceFile(
  workspaceId: string,
  nodeId: string,
  favorite: boolean,
) {
  return await request<{ id: string; favorite: boolean }>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files/favorite`,
    { method: "POST", body: JSON.stringify({ node_id: nodeId, favorite }) },
  );
}

export async function bulkDeleteWorkspaceFiles(workspaceId: string, nodeIds: string[]) {
  return await request<{ deleted: string[] }>(
    `/workspaces/${encodeURIComponent(workspaceId)}/files/bulk-delete`,
    { method: "POST", body: JSON.stringify({ node_ids: nodeIds }) },
  );
}
