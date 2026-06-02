import { post } from "./client";
import type { Deployment } from "@/types";

export async function deploy(
  conversationId: string,
  artifactId?: string,
): Promise<Deployment> {
  return await post<Deployment>("/deployments", { conversationId, artifact_id: artifactId });
}
