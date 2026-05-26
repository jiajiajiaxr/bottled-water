import { get, post } from "./client";
import type { ModelProvider, ModelConfig } from "@/types";

export async function modelProviders(): Promise<ModelProvider[]> {
  const result = await get<{ items: ModelProvider[] }>(
    "/model-providers",
  );
  return result.items;
}

export async function createModelProvider(payload: {
  name: string;
  provider_type: string;
  base_url: string;
  api_key?: string;
  default_model: string;
  supports_streaming?: boolean;
  supports_embeddings?: boolean;
  config?: Record<string, unknown>;
}): Promise<ModelProvider> {
  return await post<ModelProvider>("/model-providers", payload);
}

export async function modelConfigs(): Promise<ModelConfig[]> {
  const result = await get<{ items: ModelConfig[] }>("/model-configs");
  return result.items;
}

export async function createModelConfig(payload: {
  provider_id: string;
  name: string;
  model_id: string;
  purpose: string;
  context_window?: number;
  max_output_tokens?: number;
  temperature_default?: number;
  config?: Record<string, unknown>;
}): Promise<ModelConfig> {
  return await post<ModelConfig>("/model-configs", payload);
}

export async function testModel(
  prompt: string,
  model_config_id?: string,
): Promise<{
  response: string;
  model: string;
  usage?: Record<string, unknown>;
}> {
  return await post<{
    response: string;
    model: string;
    usage?: Record<string, unknown>;
  }>("/model-configs/test", { prompt, model_config_id });
}
