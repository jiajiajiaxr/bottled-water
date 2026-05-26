import { request } from "./client";
import type { AgentTask } from "@/types";

export async function tasks(): Promise<AgentTask[]> {
  try {
    const result = await request<{ items: AgentTask[] } | AgentTask[]>(
      "/tasks",
    );
    return Array.isArray(result) ? result : result.items;
  } catch {
    return [];
  }
}

export async function createBackgroundTask(
  conversationId: string,
  prompt: string,
): Promise<AgentTask> {
  return await request<AgentTask>("/tasks", {
    method: "POST",
    body: JSON.stringify({
      conversation_id: conversationId,
      prompt,
      title: prompt,
    }),
  });
}

export async function cancelTask(taskId: string): Promise<AgentTask> {
  return await request<AgentTask>(`/tasks/${taskId}/cancel`, {
    method: "POST",
  });
}
