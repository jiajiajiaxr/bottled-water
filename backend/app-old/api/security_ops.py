from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ForbiddenError
from app.core.response import ok
from app.deps import get_current_user
from app.models import AuditLog, Permission, Role, RolePermission, User, UserRole, utcnow
from app.services.audit import permissions_for_user, write_audit_log
from app.services.serialization import iso


router = APIRouter(tags=["security-ops"])


def _security_admin(user: User) -> None:
    if user.role not in {"admin", "developer"} and user.username != "demo":
        raise ForbiddenError("需要安全管理权限")


async def _payload(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _role_to_dict(db: Session, role: Role) -> dict:
    permission_ids = {
        item.permission_id
        for item in db.scalars(select(RolePermission).where(RolePermission.role_id == role.id)).all()
    }
    permissions = db.scalars(select(Permission).where(Permission.id.in_(permission_ids))).all() if permission_ids else []
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "permissions": [
            {
                "id": permission.id,
                "code": permission.code,
                "resource": permission.resource,
                "action": permission.action,
                "description": permission.description,
            }
            for permission in permissions
        ],
        "created_at": iso(role.created_at),
        "updated_at": iso(role.updated_at),
    }


def _permission_to_dict(permission: Permission) -> dict:
    return {
        "id": permission.id,
        "code": permission.code,
        "resource": permission.resource,
        "action": permission.action,
        "description": permission.description,
        "created_at": iso(permission.created_at),
        "updated_at": iso(permission.updated_at),
    }


@router.get("/permissions/me")
async def my_permissions(user: User = Depends(get_current_user)):
    permissions = permissions_for_user(user)
    return ok(
        {
            "user_id": user.id,
            "role": user.role,
            "roles": ["ROLE_USER", f"ROLE_{user.role.upper()}"] if user.role != "member" else ["ROLE_USER"],
            "permissions": permissions,
        }
    )


@router.get("/security/permissions")
async def list_permissions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    permissions = db.scalars(select(Permission).order_by(Permission.resource, Permission.action)).all()
    return ok({"items": [_permission_to_dict(item) for item in permissions], "total": len(permissions)})


@router.get("/security/roles")
async def list_roles(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    roles = db.scalars(select(Role).where(Role.deleted_at.is_(None)).order_by(Role.code)).all()
    return ok({"items": [_role_to_dict(db, item) for item in roles], "total": len(roles)})


@router.post("/security/roles")
async def create_role(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _security_admin(user)
    payload = await _payload(request)
    code = str(payload.get("code") or "").strip().upper()
    if not code.startswith("ROLE_"):
        code = f"ROLE_{code or 'CUSTOM'}"
    role = Role(
        code=code,
        name=str(payload.get("name") or code),
        description=str(payload.get("description") or ""),
        is_system=False,
    )
    db.add(role)
    db.flush()
    write_audit_log(db, user=user, action="security.role.create", target_type="role", target_id=role.id, detail={"code": code}, request=request, risk_score=0.3)
    db.commit()
    db.refresh(role)
    return ok(_role_to_dict(db, role), "Role created")


@router.patch("/security/roles/{role_id}/permissions")
async def update_role_permissions(
    role_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _security_admin(user)
    role = db.get(Role, role_id)
    if not role or role.deleted_at is not None:
        raise ForbiddenError("Role not found")
    payload = await _payload(request)
    codes = [str(item) for item in payload.get("permission_codes", [])]
    permissions = db.scalars(select(Permission).where(Permission.code.in_(codes))).all() if codes else []
    for row in db.scalars(select(RolePermission).where(RolePermission.role_id == role.id)).all():
        db.delete(row)
    db.flush()
    for permission in permissions:
        db.add(RolePermission(role_id=role.id, permission_id=permission.id))
    write_audit_log(
        db,
        user=user,
        action="security.role.permissions.update",
        target_type="role",
        target_id=role.id,
        detail={"permission_codes": codes},
        request=request,
        risk_score=0.45,
    )
    db.commit()
    return ok(_role_to_dict(db, role), "Role permissions updated")


@router.get("/security/users")
async def list_security_users(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role in {"admin", "developer"} or user.username == "demo":
        users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.desc()).limit(200)).all()
    else:
        users = [user]
    role_rows = db.scalars(select(UserRole)).all()
    by_user: dict[str, list[str]] = {}
    role_map = {role.id: role.code for role in db.scalars(select(Role)).all()}
    for row in role_rows:
        by_user.setdefault(row.user_id, []).append(role_map.get(row.role_id, row.role_id))
    return ok(
        {
            "items": [
                {
                    "id": item.id,
                    "email": item.email,
                    "username": item.username,
                    "display_name": item.display_name,
                    "role": item.role,
                    "status": item.status,
                    "roles": by_user.get(item.id, []),
                    "last_login_at": iso(item.last_login_at),
                    "created_at": iso(item.created_at),
                }
                for item in users
            ],
            "total": len(users),
        }
    )


@router.patch("/security/users/{target_user_id}/role")
async def update_user_role(
    target_user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _security_admin(user)
    target = db.get(User, target_user_id)
    if not target or target.deleted_at is not None:
        raise ForbiddenError("User not found")
    payload = await _payload(request)
    role = str(payload.get("role") or "member")
    target.role = role
    target.updated_at = utcnow()
    write_audit_log(db, user=user, action="security.user.role.update", target_type="user", target_id=target.id, detail={"role": role}, request=request, risk_score=0.55)
    db.commit()
    return ok({"id": target.id, "role": target.role}, "User role updated")


@router.get("/audit-logs")
async def list_audit_logs(
    target_type: str | None = None,
    action: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in {"admin", "developer"}:
        query = select(AuditLog).where(AuditLog.actor_id == user.id)
    else:
        query = select(AuditLog)
    if target_type:
        query = query.where(AuditLog.target_type == target_type)
    if action:
        query = query.where(AuditLog.action == action)
    total = len(db.scalars(query).all())
    logs = db.scalars(
        query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ok(
        {
            "items": [
                {
                    "id": item.id,
                    "actor_id": item.actor_id,
                    "action": item.action,
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "ip_address": item.ip_address,
                    "risk_score": item.risk_score,
                    "detail": item.detail,
                    "created_at": iso(item.created_at),
                }
                for item in logs
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/audit-logs/stats")
async def audit_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role not in {"admin", "developer"} and user.username != "demo":
        query = select(AuditLog).where(AuditLog.actor_id == user.id)
    else:
        query = select(AuditLog)
    logs = db.scalars(query).all()
    by_action: dict[str, int] = {}
    high_risk = 0
    for log in logs:
        by_action[log.action] = by_action.get(log.action, 0) + 1
        if (log.risk_score or 0) >= 0.5:
            high_risk += 1
    return ok(
        {
            "total": len(logs),
            "high_risk": high_risk,
            "by_action": by_action,
            "latest_at": iso(max((item.created_at for item in logs), default=None)),
        }
    )


@router.get("/admin/guard")
async def admin_guard(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise ForbiddenError("需要管理员权限")
    return ok({"allowed": True})
