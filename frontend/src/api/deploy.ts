import { request, wait } from "./client";
import { demoDeployment } from "@/mock";
import type { Deployment } from "@/types";

export async function deploy(
  conversationId: string,
  artifactId?: string,
): Promise<Deployment> {
  try {
    return await request<Deployment>("/deployments", {
      method: "POST",
      body: JSON.stringify({ conversationId, artifact_id: artifactId }),
    });
  } catch {
    await wait(500);
    return { ...demoDeployment, updatedAt: new Date().toISOString() };
  }
}
