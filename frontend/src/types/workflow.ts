export interface WorkflowNode {
  id: string;
  title: string;
  type?: "start" | "agent" | "tool" | "skill" | "mcp" | "condition" | "loop" | "review" | "artifact" | "end" | string;
  role?: string;
  status?: string;
  meta?: string;
  agent_id?: string;
  config?: Record<string, unknown>;
}

export interface ConversationWorkflow {
  conversation_id?: string;
  mode: string;
  output_mode?: "independent_messages" | "aggregate" | string;
  nodes: WorkflowNode[];
  edges: Array<string[] | { from?: string; to?: string; source?: string; target?: string; condition?: string; status?: string; config?: Record<string, unknown> }>;
  settings?: Record<string, unknown>;
}

export interface WorkflowRun {
  id: string;
  conversation_id: string;
  status: string;
  mode: string;
  workflow_snapshot: ConversationWorkflow;
  node_states: Array<WorkflowNode & { progress?: number; input?: Record<string, unknown>; output?: Record<string, unknown>; error?: string | null; message?: string; started_at?: string; completed_at?: string }>;
  edge_states: Array<{ from: string; to: string; condition?: string; status: string }>;
  events: Array<Record<string, unknown>>;
  progress: number;
  started_at?: string;
  completed_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface AgentTask {
  id: string;
  task_id?: string;
  conversation_id?: string;
  title: string;
  description?: string;
  status: string;
  priority?: string;
  progress?: number;
  plan?: Record<string, unknown>;
  output?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}
