import { get, post } from "./client";
import type { RemoteConnection } from "@/types";

export async function remoteConnections(): Promise<RemoteConnection[]> {
  const result = await get<{ items: RemoteConnection[] }>(
    "/remote-connections",
  );
  return result.items;
}

export async function createRemoteConnection(payload: {
  workspace_id?: string;
  name: string;
  connection_type: string;
  endpoint: string;
  capabilities?: string[];
}): Promise<RemoteConnection> {
  return await post<RemoteConnection>("/remote-connections", payload);
}

export async function connectRemote(id: string): Promise<RemoteConnection> {
  return await post<RemoteConnection>(
    `/remote-connections/${id}/connect`,
    {},
  );
}
