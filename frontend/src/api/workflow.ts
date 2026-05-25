import { request } from "./client";
import type { ConversationWorkflow, WorkflowRun } from "../types";

export async function conversationWorkflow(
  conversationId: string,
): Promise<ConversationWorkflow> {
  return await request<ConversationWorkflow>(
    `/conversations/${conversationId}/workflow`,
  );
}

export async function saveConversationWorkflow(
  conversationId: string,
  workflow: ConversationWorkflow,
): Promise<ConversationWorkflow> {
  return await request<ConversationWorkflow>(
    `/conversations/${conversationId}/workflow`,
    {
      method: "PATCH",
      body: JSON.stringify(workflow),
    },
  );
}

export async function generateConversationWorkflow(
  conversationId: string,
  instruction?: string,
): Promise<ConversationWorkflow> {
  return await request<ConversationWorkflow>(
    `/conversations/${conversationId}/workflow/generate`,
    {
      method: "POST",
      body: JSON.stringify({ instruction: instruction ?? "" }),
    },
  );
}

export async function workflowRuns(conversationId: string): Promise<WorkflowRun[]> {
  const result = await request<{ items: WorkflowRun[] }>(
    `/conversations/${conversationId}/workflow/runs`,
  );
  return result.items;
}

export async function startWorkflowRun(
  conversationId: string,
  workflow?: ConversationWorkflow,
): Promise<WorkflowRun> {
  return await request<WorkflowRun>(
    `/conversations/${conversationId}/workflow/runs`,
    {
      method: "POST",
      body: JSON.stringify({ workflow }),
    },
  );
}

export async function updateWorkflowNode(
  conversationId: string,
  runId: string,
  nodeId: string,
  payload: {
    status: string;
    progress?: number;
    output?: Record<string, unknown>;
    message?: string;
  },
): Promise<WorkflowRun> {
  return await request<WorkflowRun>(
    `/conversations/${conversationId}/workflow/runs/${runId}/nodes/${encodeURIComponent(nodeId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}
