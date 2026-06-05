import { get, post } from "./client";
import type { ExternalAgentProbeResponse, ExternalAgentRun } from "@/types";

export async function externalAgentProbe(
  provider?: string,
): Promise<ExternalAgentProbeResponse> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return await get<ExternalAgentProbeResponse>(`/external-agents/probe${query}`);
}

export async function reprobeExternalAgent(
  provider?: string,
): Promise<ExternalAgentProbeResponse> {
  const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
  return await post<ExternalAgentProbeResponse>(
    `/external-agents/probe${query}`,
    {},
  );
}

export async function externalAgentRuns(
  workspaceId?: string,
  limit = 20,
): Promise<ExternalAgentRun[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (workspaceId) params.set("workspace_id", workspaceId);
  const result = await get<{ items: ExternalAgentRun[] }>(
    `/external-agents/runs?${params.toString()}`,
  );
  return result.items;
}
