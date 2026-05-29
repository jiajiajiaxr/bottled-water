export interface Workspace {
  id: string;
  name: string;
  description: string;
  type: string;
  status: string;
  tags: string[];
  member_count: number;
  project_count: number;
  workflow?: Record<string, unknown>;
  config?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  type: string;
  status: string;
  tags: string[];
  file_count: number;
  current_version: number;
  created_at?: string;
  updated_at?: string;
}

export interface WorkspaceFileNode {
  id: string;
  name: string;
  type: "file" | "directory" | string;
  path: string;
  size?: number;
  updated_at?: string;
  source: string;
  mime_type?: string;
  download_url?: string;
  preview_url?: string;
  children?: WorkspaceFileNode[];
}

export interface WorkspaceFileTree {
  workspace_id: string;
  root: WorkspaceFileNode;
  items: WorkspaceFileNode[];
}

export interface WorkspaceFilePreview {
  type?: string;
  mode?: "text" | "pdf" | "image" | "office_text" | string;
  text?: string;
  preview_text?: string;
  content_type?: string;
  filename?: string;
  download_url?: string;
  metadata?: Record<string, unknown>;
}
