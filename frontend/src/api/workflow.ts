import { get, post, patch } from "./client";
import type { ConversationWorkflow, WorkflowRun } from "@/types";

export async function conversationWorkflow(
  conversationId: string,
): Promise<ConversationWorkflow> {
  return await get<ConversationWorkflow>(
    `/conversations/${conversationId}/workflow`,
  );
}

export async function saveConversationWorkflow(
  conversationId: string,
  workflow: ConversationWorkflow,
): Promise<ConversationWorkflow> {
  return await patch<ConversationWorkflow>(
    `/conversations/${conversationId}/workflow`,
    workflow,
  );
}

export async function generateConversationWorkflow(
  conversationId: string,
  instruction?: string,
): Promise<ConversationWorkflow> {
  return await post<ConversationWorkflow>(
    `/conversations/${conversationId}/workflow/generate`,
    { instruction: instruction ?? "" },
  );
}

export async function workflowRuns(conversationId: string): Promise<WorkflowRun[]> {
  const result = await get<{ items: WorkflowRun[] }>(
    `/conversations/${conversationId}/workflow/runs`,
  );
  return result.items;
}

export async function startWorkflowRun(
  conversationId: string,
  workflow?: ConversationWorkflow,
): Promise<WorkflowRun> {
  return await post<WorkflowRun>(
    `/conversations/${conversationId}/workflow/runs`,
    { workflow },
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
  return await patch<WorkflowRun>(
    `/conversations/${conversationId}/workflow/runs/${runId}/nodes/${encodeURIComponent(nodeId)}`,
    payload,
  );
}
