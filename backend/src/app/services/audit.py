from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User


ROLE_PERMISSIONS = {
    "member": {
        "session:create",
        "session:read",
        "session:delete",
        "session:export",
        "agent:use",
        "log:view:own",
        "api_key:manage",
        "billing:view",
        "workspace:create",
        "workspace:read",
        "project:manage",
        "knowledge:manage",
        "file:upload",
        "artifact:export",
        "workflow:manage",
        "mcp:invoke",
        "security:view",
    },
    "agent_provider": {
        "agent:create",
        "agent:update",
        "agent:delete",
        "agent:publish",
        "agent:debug",
    },
    "developer": {"log:view:all", "config:debug"},
    "admin": {"user:manage", "config:manage", "log:view:all", "billing:manage", "agent:publish"},
}


def permissions_for_user(user: User) -> list[str]:
    permissions = set(ROLE_PERMISSIONS["member"])
    if user.role in {"agent_provider", "developer", "admin"}:
        permissions |= ROLE_PERMISSIONS["agent_provider"]
    if user.role in {"developer", "admin"}:
        permissions |= ROLE_PERMISSIONS["developer"]
    if user.role == "admin":
        permissions |= ROLE_PERMISSIONS["admin"]
    return sorted(permissions)


def has_permission(user: User, permission: str) -> bool:
    return permission in permissions_for_user(user)


async def write_audit_log(
    db: AsyncSession,
    *,
    user: User | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
    detail: dict | None = None,
    request: Request | None = None,
    risk_score: float = 0,
) -> AuditLog:
    log = AuditLog(
        actor_id=user.id if user else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
        risk_score=risk_score,
        detail=detail or {},
    )
    await db.add(log)
    return log
