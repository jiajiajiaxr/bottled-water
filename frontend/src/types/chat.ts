import type { ConversationWorkflow, WorkflowRun } from "./workflow";

export type MessageRole = "user" | "assistant" | "system" | "tool";
export type MessageKind = "text" | "code" | "file" | "event" | "error" | "preview_card" | "diff_panel" | "deploy_status_card";
export type StreamState = "idle" | "streaming" | "done" | "error";

export interface Participant {
  id?: string;
  participant_id?: string;
  participant_type?: "agent" | "user";
  user_id?: string;
  agent_id?: string;
  agent_name?: string;
  agent_type?: string;
  agent_status?: string;
  agent_avatar_url?: string;
  role?: "owner" | "admin" | "member";
  nickname?: string;
  joined_at?: string;
}

export interface Conversation {
  id: string;
  chat_type?: "single" | "group";
  title: string;
  participants: Participant[];
  participant_count?: number;
  agent_count?: number;
  user_count?: number;
  master_enabled?: boolean;
  updatedAt: string;
  pinned: boolean;
  archived: boolean;
  unread: number;
  tags: string[];
  category?: string;
  folder?: string;
  remark?: string;
  workspace_id?: string;
  lastMessage: string;
  workflow?: ConversationWorkflow;
  workflow_runtime?: WorkflowRun;
}

export interface MessageAttachment {
  id?: string;
  file_id?: string;
  filename?: string;
  original_filename?: string;
  content_type?: string;
  size?: number;
  parse_status?: string;
  extracted_text?: string;
  public_url?: string;
  url?: string;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  sender_id?: string;
  sender_type?: string;
  role: MessageRole;
  kind: MessageKind;
  author: string;
  content: string;
  thinking?: string;
  rawContent?: Record<string, unknown>;
  attachments?: MessageAttachment[];
  createdAt: string;
  streamState?: StreamState;
  quotedMessageId?: string;
  status?: string;
}

export interface WorkspaceArtifact {
  id: string;
  conversationId: string;
  type?: string;
  format?: string;
  media_type?: string;
  filename?: string;
  title: string;
  language: string;
  code: string;
  previousCode: string;
  previewUrl?: string;
  preview_url?: string;
  content?: {
    preview_html?: string;
    format?: string;
    media_type?: string;
    filename?: string;
    tool_output?: {
      format?: string;
      media_type?: string;
      filename?: string;
    };
    files?: Record<string, string>;
  };
  updatedAt: string;
}

export interface Deployment {
  id: string;
  status: "idle" | "building" | "ready" | "failed" | "deployed" | "deploying" | "pending";
  url?: string;
  commit: string;
  updatedAt: string;
}
