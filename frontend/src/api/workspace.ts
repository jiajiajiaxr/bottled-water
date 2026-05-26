import { get, post, request } from "./client";
import type { Workspace, Project } from "@/types";

export async function workspaces(): Promise<Workspace[]> {
  const result = await get<{ items: Workspace[] }>("/workspaces");
  return result.items;
}

export async function createWorkspace(payload: {
  name: string;
  description: string;
  type: string;
  tags: string[];
  config?: Record<string, unknown>;
}): Promise<Workspace> {
  return await post<Workspace>("/workspaces", payload);
}

export async function projects(workspaceId: string): Promise<Project[]> {
  const result = await get<{ items: Project[] }>(
    `/workspaces/${workspaceId}/projects`,
  );
  return result.items;
}

export async function createProject(
  workspaceId: string,
  payload: { name: string; description: string; type: string },
): Promise<Project> {
  return await post<Project>(`/workspaces/${workspaceId}/projects`, payload);
}

export async function saveProjectFile(
  projectId: string,
  payload: { path: string; language: string; content: string },
): Promise<{ path: string; version: number }> {
  return await request<{ path: string; version: number }>(
    `/projects/${projectId}/files`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}
