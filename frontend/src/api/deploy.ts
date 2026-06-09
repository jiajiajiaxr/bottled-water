import { get, post } from "./client";
import type { Deployment } from "@/types";

export async function deploy(
  conversationId: string,
  artifactId?: string,
): Promise<Deployment> {
  return await post<Deployment>("/deployments", {
    conversationId,
    artifact_id: artifactId,
    mode: "static_site",
  });
}

export async function deploymentsForArtifact(
  artifactId: string,
): Promise<{ items: Deployment[]; total: number }> {
  return await get<{ items: Deployment[]; total: number }>(
    `/artifacts/${artifactId}/deployments`,
  );
}
