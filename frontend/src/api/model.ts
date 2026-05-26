import { request } from "./client";
import { demoModelProviders, demoModelConfigs } from "@/mock";
import type { ModelProvider, ModelConfig } from "@/types";

export async function modelProviders(): Promise<ModelProvider[]> {
  try {
    const result = await request<{ items: ModelProvider[] }>(
      "/model-providers",
    );
    return result.items;
  } catch {
    return demoModelProviders;
  }
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
  try {
    return await request<ModelProvider>("/model-providers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `provider-${Date.now()}`,
      name: payload.name,
      provider_type: payload.provider_type,
      base_url: payload.base_url,
      default_model: payload.default_model,
      supports_streaming: payload.supports_streaming ?? true,
      supports_embeddings: payload.supports_embeddings ?? false,
      config: payload.config,
      status: "active",
    };
  }
}

export async function modelConfigs(): Promise<ModelConfig[]> {
  try {
    const result = await request<{ items: ModelConfig[] }>("/model-configs");
    return result.items;
  } catch {
    return demoModelConfigs;
  }
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
  try {
    return await request<ModelConfig>("/model-configs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      id: `model-${Date.now()}`,
      provider_id: payload.provider_id,
      name: payload.name,
      model_id: payload.model_id,
      purpose: payload.purpose,
      context_window: payload.context_window ?? 128000,
      max_output_tokens: payload.max_output_tokens ?? 4096,
      temperature_default: payload.temperature_default ?? 0.4,
      config: payload.config,
      status: "active",
    };
  }
}

export async function testModel(
  prompt: string,
  model_config_id?: string,
): Promise<{
  response: string;
  model: string;
  usage?: Record<string, unknown>;
}> {
  return await request<{
    response: string;
    model: string;
    usage?: Record<string, unknown>;
  }>("/model-configs/test", {
    method: "POST",
    body: JSON.stringify({ prompt, model_config_id }),
  });
}
