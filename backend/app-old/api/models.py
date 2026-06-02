from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError
from app.core.response import ok
from app.deps import get_current_user
from app.models import ModelConfig, ModelProvider, User, utcnow
from app.schemas.requests import CreateModelConfigRequest, CreateModelProviderRequest, TestModelRequest
from app.services.llm_gateway import test_model_config
from app.services.serialization import model_config_to_dict, model_provider_to_dict


router = APIRouter(tags=["model-management"])


def ensure_model_tables(db: Session) -> None:
    for table in (ModelProvider.__table__, ModelConfig.__table__):
        table.create(bind=db.get_bind(), checkfirst=True)


def _get_provider(db: Session, user: User, provider_id: str) -> ModelProvider:
    ensure_model_tables(db)
    provider = db.scalar(
        select(ModelProvider)
        .options(selectinload(ModelProvider.models))
        .where(ModelProvider.id == provider_id, ModelProvider.deleted_at.is_(None))
    )
    if not provider:
        raise NotFoundError("模型供应商不存在")
    if provider.owner_id not in {None, user.id} and user.role != "admin":
        raise ForbiddenError("无权访问该模型供应商")
    return provider


@router.get("/model-providers")
async def list_model_providers(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_model_tables(db)
    providers = db.scalars(
        select(ModelProvider)
        .options(selectinload(ModelProvider.models))
        .where(ModelProvider.deleted_at.is_(None))
        .where((ModelProvider.owner_id == user.id) | (ModelProvider.owner_id.is_(None)))
        .order_by(ModelProvider.created_at.desc())
    ).all()
    return ok({"items": [model_provider_to_dict(item) for item in providers], "total": len(providers)})


@router.post("/model-providers")
async def create_model_provider(
    payload: CreateModelProviderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_model_tables(db)
    provider = ModelProvider(
        owner_id=user.id,
        name=payload.name,
        provider_type=payload.provider_type,
        base_url=payload.base_url.rstrip("/"),
        api_key_ref=payload.api_key or "mock",
        default_model=payload.default_model,
        supports_streaming=payload.supports_streaming,
        supports_embeddings=payload.supports_embeddings,
        config=payload.config,
        status="active",
    )
    db.add(provider)
    db.flush()
    model = ModelConfig(
        provider_id=provider.id,
        name=payload.default_model,
        model_id=payload.default_model,
        purpose="chat",
        config={"created_from_provider": True},
    )
    db.add(model)
    db.commit()
    db.refresh(provider)
    return ok(model_provider_to_dict(_get_provider(db, user, provider.id)), "模型供应商已创建")


@router.patch("/model-providers/{provider_id}")
async def update_model_provider(
    provider_id: str,
    payload: CreateModelProviderRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = _get_provider(db, user, provider_id)
    if provider.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只有创建者可修改模型供应商")
    provider.name = payload.name
    provider.provider_type = payload.provider_type
    provider.base_url = payload.base_url.rstrip("/")
    if payload.api_key:
        provider.api_key_ref = payload.api_key
    provider.default_model = payload.default_model
    provider.supports_streaming = payload.supports_streaming
    provider.supports_embeddings = payload.supports_embeddings
    provider.config = payload.config
    db.commit()
    return ok(model_provider_to_dict(provider), "模型供应商已更新")


@router.delete("/model-providers/{provider_id}")
async def delete_model_provider(
    provider_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = _get_provider(db, user, provider_id)
    if provider.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只有创建者可删除模型供应商")
    provider.deleted_at = utcnow()
    provider.status = "deleted"
    db.commit()
    return ok({"id": provider.id, "deleted": True})


@router.get("/model-configs")
async def list_model_configs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_model_tables(db)
    configs = db.scalars(
        select(ModelConfig)
        .options(selectinload(ModelConfig.provider))
        .join(ModelProvider)
        .where(ModelConfig.deleted_at.is_(None), ModelProvider.deleted_at.is_(None))
        .where((ModelProvider.owner_id == user.id) | (ModelProvider.owner_id.is_(None)))
        .order_by(ModelConfig.updated_at.desc())
    ).all()
    return ok({"items": [model_config_to_dict(item) for item in configs], "total": len(configs)})


@router.post("/model-configs")
async def create_model_config(
    payload: CreateModelConfigRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    provider = _get_provider(db, user, payload.provider_id)
    config = ModelConfig(
        provider_id=provider.id,
        name=payload.name,
        model_id=payload.model_id,
        purpose=payload.purpose,
        context_window=payload.context_window,
        max_output_tokens=payload.max_output_tokens,
        temperature_default=payload.temperature_default,
        config=payload.config,
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return ok(model_config_to_dict(config), "模型配置已创建")


@router.post("/model-configs/test")
async def test_model(
    payload: TestModelRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_model_tables(db)
    model_id = payload.model_config_id
    if not model_id:
        model = db.scalar(
            select(ModelConfig)
            .join(ModelProvider)
            .where(ModelConfig.deleted_at.is_(None), ModelProvider.deleted_at.is_(None))
            .where((ModelProvider.owner_id == user.id) | (ModelProvider.owner_id.is_(None)))
            .order_by(ModelConfig.created_at.asc())
        )
        if not model:
            raise NotFoundError("暂无可测试模型")
        model_id = model.id
    result = await test_model_config(db, model_id, payload.prompt)
    return ok({"response": result.text, "model": result.model, "usage": result.usage}, "模型测试完成")
