import { request } from "./client";
import { demoWorkspaces, demoProjects } from "../mock";
import type { Workspace, Project } from "../types";

export async function workspaces(): Promise<Workspace[]> {
  try {
    const result = await request<{ items: Workspace[] }>("/workspaces");
    return result.items;
  } catch {
    return demoWorkspaces;
  }
}

export async function createWorkspace(payload: {
  name: string;
  description: string;
  type: string;
  tags: string[];
  config?: Record<string, unknown>;
}): Promise<Workspace> {
  try {
    return await request<Workspace>("/workspaces", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `workspace-${Date.now()}`,
      status: "active",
      member_count: 1,
      project_count: 0,
      ...payload,
    };
  }
}

export async function projects(workspaceId: string): Promise<Project[]> {
  try {
    const result = await request<{ items: Project[] }>(
      `/workspaces/${workspaceId}/projects`,
    );
    return result.items;
  } catch {
    return demoProjects.filter(
      (project) => project.workspace_id === workspaceId,
    );
  }
}

export async function createProject(
  workspaceId: string,
  payload: { name: string; description: string; type: string },
): Promise<Project> {
  try {
    return await request<Project>(`/workspaces/${workspaceId}/projects`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `project-${Date.now()}`,
      workspace_id: workspaceId,
      status: "active",
      tags: [],
      file_count: 0,
      current_version: 1,
      ...payload,
    };
  }
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
