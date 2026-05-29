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
  display_name?: string;
  type: "file" | "directory" | string;
  path: string;
  display_path?: string;
  size?: number;
  updated_at?: string;
  source: string;
  mime_type?: string;
  download_url?: string;
  preview_url?: string;
  favorite?: boolean;
  children?: WorkspaceFileNode[];
}

export interface WorkspaceFileTree {
  workspace_id: string;
  root: WorkspaceFileNode;
  items: WorkspaceFileNode[];
  stats?: {
    file_count: number;
    directory_count: number;
    total_size: number;
    source_counts?: Record<string, number>;
  };
}

export interface WorkspaceFilePreview {
  type?: string;
  mode?: "text" | "markdown" | "html" | "pdf" | "image" | "office_text" | "binary" | string;
  text?: string;
  preview_text?: string;
  content_type?: string;
  original_content_type?: string;
  filename?: string;
  artifact_id?: string;
  artifact_type?: string;
  preview_url?: string;
  preview_pdf_url?: string;
  preview_download_url?: string;
  preview_error?: string;
  download_url?: string;
  office_preview?: { cached?: boolean };
  metadata?: Record<string, unknown>;
}
