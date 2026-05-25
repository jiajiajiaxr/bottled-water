export interface ModelProvider {
  id: string;
  name: string;
  provider_type: string;
  base_url: string;
  default_model: string;
  supports_streaming: boolean;
  supports_embeddings: boolean;
  status: string;
  config?: Record<string, unknown>;
  models?: ModelConfig[];
  created_at?: string;
  updated_at?: string;
}

export interface ModelConfig {
  id: string;
  provider_id: string;
  provider_name?: string;
  name: string;
  model_id: string;
  purpose: string;
  context_window: number;
  max_output_tokens: number;
  temperature_default: number;
  config?: Record<string, unknown>;
  status: string;
  created_at?: string;
  updated_at?: string;
}
