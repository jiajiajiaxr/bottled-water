import { request } from "./client";
import { demoRemoteConnections } from "@/mock";
import type { RemoteConnection } from "@/types";

export async function remoteConnections(): Promise<RemoteConnection[]> {
  try {
    const result = await request<{ items: RemoteConnection[] }>(
      "/remote-connections",
    );
    return result.items;
  } catch {
    return demoRemoteConnections;
  }
}

export async function createRemoteConnection(payload: {
  workspace_id?: string;
  name: string;
  connection_type: string;
  endpoint: string;
  capabilities?: string[];
}): Promise<RemoteConnection> {
  try {
    return await request<RemoteConnection>("/remote-connections", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `remote-${Date.now()}`,
      workspace_id: payload.workspace_id,
      name: payload.name,
      connection_type: payload.connection_type,
      endpoint: payload.endpoint,
      capabilities: payload.capabilities ?? [],
      status: "disconnected",
    };
  }
}

export async function connectRemote(id: string): Promise<RemoteConnection> {
  try {
    return await request<RemoteConnection>(
      `/remote-connections/${id}/connect`,
      { method: "POST" },
    );
  } catch {
    const current =
      demoRemoteConnections.find((item) => item.id === id) ??
      demoRemoteConnections[0];
    return {
      ...current,
      status: "connected",
      last_connected_at: new Date().toISOString(),
    };
  }
}
