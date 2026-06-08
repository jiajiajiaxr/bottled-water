export interface User {
  id: string;
  name: string;
  avatar?: string;
  avatar_url?: string;
  signature?: string;
  role: "demo" | "member" | "admin" | string;
  default_model_config_id?: string;
}
