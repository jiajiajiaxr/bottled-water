import { get, post } from "./client";
import type { AgentTask } from "@/types";

export async function tasks(): Promise<AgentTask[]> {
  const result = await get<{ items: AgentTask[] } | AgentTask[]>("/tasks");
  return Array.isArray(result) ? result : result.items;
}

export async function createBackgroundTask(
  conversationId: string,
  prompt: string,
): Promise<AgentTask> {
  return await post<AgentTask>("/tasks", {
    conversation_id: conversationId,
    prompt,
    title: prompt,
  });
}

export async function cancelTask(taskId: string): Promise<AgentTask> {
  return await post<AgentTask>(`/tasks/${taskId}/cancel`, {});
}
