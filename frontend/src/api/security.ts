import { get } from "./client";
import type { AuditLog, SecurityPermission, SecurityRole, SecurityUser } from "@/types";

export async function auditLogs(): Promise<AuditLog[]> {
  const result = await get<{ items: AuditLog[] }>(
    "/audit-logs?page_size=100",
  );
  return result.items;
}

export async function auditStats(): Promise<{
  total: number;
  high_risk: number;
  by_action: Record<string, number>;
  latest_at?: string;
}> {
  return await get<{
    total: number;
    high_risk: number;
    by_action: Record<string, number>;
    latest_at?: string;
  }>("/audit-logs/stats");
}

export async function securityRoles(): Promise<SecurityRole[]> {
  const result = await get<{ items: SecurityRole[] }>("/security/roles");
  return result.items;
}

export async function securityPermissions(): Promise<SecurityPermission[]> {
  const result = await get<{ items: SecurityPermission[] }>(
    "/security/permissions",
  );
  return result.items;
}

export async function securityUsers(): Promise<SecurityUser[]> {
  const result = await get<{ items: SecurityUser[] }>("/security/users");
  return result.items;
}
