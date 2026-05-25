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
