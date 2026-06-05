import { get, post } from "./client";
import type { SandboxSession, SandboxCommandResult } from "@/types";

export async function sandboxes(): Promise<SandboxSession[]> {
  const result = await get<{ items: SandboxSession[] }>("/sandboxes");
  return result.items;
}

export async function createSandbox(payload: {
  workspace_id?: string;
  project_id?: string;
  name: string;
  image: string;
  resource_limits?: Record<string, unknown>;
}): Promise<SandboxSession> {
  return await post<SandboxSession>("/sandboxes", payload);
}

export async function runSandboxCommand(
  sandboxId: string,
  payload: {
    command: string;
    timeout_seconds?: number;
    cwd?: string;
    env?: Record<string, string>;
  },
): Promise<{ sandbox: SandboxSession; result: SandboxCommandResult }> {
  return await post<{
    sandbox: SandboxSession;
    result: SandboxCommandResult;
  }>(`/sandboxes/${sandboxId}/commands`, payload);
}

export async function runMessageCodeBlock(
  conversationId: string,
  messageId: string,
  payload: {
    language: string;
    code: string;
    index: number;
    timeout_seconds?: number;
    workspace_id?: string;
    conversation_id?: string;
    message_id?: string;
  },
): Promise<SandboxCommandResult & Record<string, unknown>> {
  return await post<SandboxCommandResult & Record<string, unknown>>(
    `/conversations/${conversationId}/messages/${messageId}/code-runs`,
    payload,
  );
}
