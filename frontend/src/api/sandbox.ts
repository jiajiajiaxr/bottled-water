import { request } from "./client";
import { demoSandboxes } from "../mock";
import type { SandboxSession, SandboxCommandResult } from "../types";

export async function sandboxes(): Promise<SandboxSession[]> {
  try {
    const result = await request<{ items: SandboxSession[] }>("/sandboxes");
    return result.items;
  } catch {
    return demoSandboxes;
  }
}

export async function createSandbox(payload: {
  workspace_id?: string;
  project_id?: string;
  name: string;
  image: string;
  resource_limits?: Record<string, unknown>;
}): Promise<SandboxSession> {
  try {
    return await request<SandboxSession>("/sandboxes", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `sandbox-${Date.now()}`,
      workspace_id: payload.workspace_id,
      project_id: payload.project_id,
      name: payload.name,
      image: payload.image,
      resource_limits: payload.resource_limits,
      status: "ready",
      mounted_files: [],
      command_history: [],
    };
  }
}

export async function runSandboxCommand(
  sandboxId: string,
  payload: {
    command: string;
    timeout_seconds?: number;
    workdir?: string;
    cwd?: string;
    env?: Record<string, string>;
  },
): Promise<{ sandbox: SandboxSession; result: SandboxCommandResult }> {
  try {
    return await request<{
      sandbox: SandboxSession;
      result: SandboxCommandResult;
    }>(`/sandboxes/${sandboxId}/commands`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    const result: SandboxCommandResult = {
      status: "fallback",
      capability_level: "fallback",
      sandbox_id: sandboxId,
      command: payload.command,
      argv: payload.command.split(" "),
      cwd: payload.cwd || payload.workdir || "",
      exit_code: 0,
      stdout: `[mock-sandbox] ${payload.command}`,
      stderr: "",
      duration_ms: 300,
      created_at: new Date().toISOString(),
    };
    const sandbox =
      demoSandboxes.find((item) => item.id === sandboxId) ?? demoSandboxes[0];
    return {
      sandbox: {
        ...sandbox,
        command_history: [result, ...sandbox.command_history],
      },
      result,
    };
  }
}
