export interface AuditLog {
  id: string;
  actor_id?: string;
  action: string;
  target_type: string;
  target_id?: string;
  ip_address?: string;
  risk_score: number;
  detail: Record<string, unknown>;
  created_at?: string;
}

export interface SecurityPermission {
  id: string;
  code: string;
  resource: string;
  action: string;
  description?: string;
}

export interface SecurityRole {
  id: string;
  code: string;
  name: string;
  description?: string;
  is_system: boolean;
  permissions: SecurityPermission[];
}

export interface SecurityUser {
  id: string;
  email: string;
  username: string;
  display_name: string;
  role: string;
  status: string;
  roles: string[];
  last_login_at?: string;
  created_at?: string;
}
