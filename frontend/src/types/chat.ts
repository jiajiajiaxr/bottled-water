import type { ConversationWorkflow, WorkflowRun } from "./workflow";

export type MessageRole = "user" | "assistant" | "system" | "tool";
export type MessageKind =
  | "text"
  | "code"
  | "file"
  | "event"
  | "error"
  | "preview_card"
  | "diff_panel"
  | "deploy_status_card";
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
  left_at?: string;
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

export interface ToolEventRecord {
  toolName: string;
  toolCallId?: string;
  status?: string;
  exit_code?: number | string;
  duration_ms?: number | string;
  stdout?: string;
  stderr?: string;
  summary?: string;
  error?: string;
}

export interface ChatMessage {
  id: string; // 消息 ID，目前使用agent_id
  conversationId: string; // 对话 ID，不清楚来源
  sender_id?: string; // 不清楚作用
  sender_type?: string; // 不清楚作用
  role: MessageRole; // 不清楚作用
  kind: MessageKind; // 不清楚作用
  author: string; // 不清楚作用
  content: string; // 消息内容
  thinking?: string; // LLM思考内容
  rawContent?: Record<string, unknown>; // 不清楚作用
  attachments?: MessageAttachment[]; // 消息附件
  toolEvents?: ToolEventRecord[]; // 工具执行事件
  createdAt: string; // 不清楚作用
  streamState?: StreamState; // 流式状态，根据其情况确定组件是否需要更新
  quotedMessageId?: string; // 引用的消息 ID，不清楚来源
  status?: string; // 不清楚作用
  state: "active" | "inactive"; // 旧的流式状态，之后会移除
}

export interface WorkspaceArtifact {
  id: string;
  conversationId: string;
  title: string;
  language: string;
  code: string;
  previousCode: string;
  previewUrl?: string;
  updatedAt: string;
  /** 扩展字段，用于支持多种格式的 artifact */
  content?: {
    format?: string;
    media_type?: string;
    filename?: string;
    preview_html?: string;
    files?: Record<string, string>;
    tool_output?: {
      format?: string;
      media_type?: string;
      filename?: string;
    };
  };
  format?: string;
  type?: "document" | "spreadsheet" | "slides" | string;
  media_type?: string;
  filename?: string;
}

export interface Deployment {
  id: string;
  status:
    | "idle"
    | "building"
    | "ready"
    | "failed"
    | "deployed"
    | "deploying"
    | "pending";
  url?: string;
  commit: string;
  updatedAt: string;
}
