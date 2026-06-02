from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import UnauthorizedError, ValidationAppError
from app.core.response import ok
from app.core.security import create_access_token, hash_password, verify_password
from app.deps import get_current_user
from app.models import User, UserSettings, utcnow
from app.schemas.common import ApiResponse, UserOut, UserResponse
from app.schemas.requests import ChangePasswordRequest, LoginRequest, RegisterRequest, UpdateProfileRequest
from app.services.seed import ensure_seed_data
from app.services.serialization import user_to_dict


router = APIRouter(tags=["auth"])
compat_router = APIRouter(tags=["auth-compat"])


async def _find_user(db: AsyncSession, username_or_email: str) -> User | None:
    return await db.scalar(
        select(User).where(
            or_(User.email == username_or_email, User.username == username_or_email),
            User.deleted_at.is_(None),
        )
    )


def _login_response(user: User) -> dict:
    token = create_access_token(user.id, {"email": user.email, "role": user.role})
    return {"access_token": token, "token": token, "user": user_to_dict(user)}


async def _register(db: AsyncSession, payload: dict) -> tuple[dict, int]:
    email = payload.get("email") or payload.get("username") or "demo@agenthub.local"
    username = payload.get("username") or payload.get("name") or email.split("@")[0]
    password = payload.get("password") or get_settings().demo_password
    if not email or not username or not password:
        raise ValidationAppError("邮箱、用户名和密码不能为空")
    existing = await _find_user(db, email) or await _find_user(db, username)
    if existing:
        return _login_response(existing), 409
    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        display_name=payload.get("display_name") or payload.get("name") or username,
    )
    db.add(user)
    await db.flush()
    db.add(UserSettings(user_id=user.id, theme="light"))
    await db.commit()
    await db.refresh(user)
    return _login_response(user), 201


async def _login(db: AsyncSession, payload: dict) -> dict:
    settings = get_settings()
    if payload.get("demo") or payload.get("name") == "demo":
        user = await ensure_seed_data(db)
        return _login_response(user)
    username = payload.get("username") or payload.get("email") or payload.get("name")
    password = payload.get("password") or settings.demo_password
    if not username:
        user = await ensure_seed_data(db)
        return _login_response(user)
    user = await _find_user(db, username)
    if not user or not verify_password(password, user.password_hash):
        raise UnauthorizedError("用户名或密码错误")
    user.last_login_at = utcnow()
    user.login_count += 1
    await db.commit()
    await db.refresh(user)
    return _login_response(user)


@router.post("/auth/register", response_model=ApiResponse[dict])
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    data, _ = await _register(db, payload.model_dump())
    return ok(data, "注册成功")


@router.post("/auth/signup", response_model=ApiResponse[dict])
async def signup_alias(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    data, _ = await _register(db, payload.model_dump())
    return ok(data, "注册成功")


@router.post("/auth/login", response_model=ApiResponse[dict])
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    return ok(await _login(db, payload.model_dump()), "登录成功")


@router.post("/auth/demo", response_model=ApiResponse[dict])
async def demo_login(db: AsyncSession = Depends(get_db)):
    return ok(_login_response(await ensure_seed_data(db)), "演示用户已登录")


@router.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return ok(user_to_dict(user))


@router.post("/auth/logout", response_model=ApiResponse[dict])
async def logout():
    return ok({"ok": True}, "已退出")


@router.patch("/auth/me", response_model=UserResponse)
async def update_me(
    payload: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = payload.model_dump(exclude_unset=True)
    display_name = str(
        raw.get("display_name") or raw.get("name") or user.display_name,
    ).strip()
    if not display_name:
        raise ValidationAppError("display name cannot be empty")
    user.display_name = display_name[:100]
    if "avatar_url" in raw:
        user.avatar_url = str(raw.get("avatar_url") or "") or None
    if isinstance(raw.get("settings"), dict):
        if not user.settings:
            db.add(UserSettings(user_id=user.id, theme="light"))
            await db.flush()
        user.extra = {**(user.extra or {}), "ui_settings": raw["settings"]}
    await db.commit()
    await db.refresh(user)
    return ok(user_to_dict(user), "profile updated")


@router.post("/auth/password", response_model=ApiResponse[dict])
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    raw = payload.model_dump(exclude_unset=True)
    current_password = str(raw.get("current_password") or raw.get("old_password") or "")
    new_password = str(raw.get("new_password") or raw.get("password") or "")
    if not current_password or not new_password:
        raise ValidationAppError("current password and new password are required")
    if len(new_password) < 6:
        raise ValidationAppError("new password must be at least 6 characters")
    if not verify_password(current_password, user.password_hash):
        raise UnauthorizedError("current password is incorrect")
    user.password_hash = hash_password(new_password)
    await db.commit()
    return ok({"changed": True}, "password updated")


async def _compat_payload(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


@compat_router.post("/auth/signup")
async def compat_signup(request: Request, db: AsyncSession = Depends(get_db)):
    data, status = await _register(db, await _compat_payload(request))
    return data if status != 409 else data


@compat_router.post("/auth/login")
async def compat_login(request: Request, db: AsyncSession = Depends(get_db)):
    return await _login(db, await _compat_payload(request))


@compat_router.get("/auth/me")
async def compat_me(user: User = Depends(get_current_user)):
    return user_to_dict(user)
