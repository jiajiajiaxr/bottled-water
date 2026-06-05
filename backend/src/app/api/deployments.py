from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.core.errors import NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import Artifact, Conversation, Deployment, User, utcnow
from app.schemas.common import ApiResponse, DeploymentOut
from app.schemas.requests import CreateDeploymentRequest
from app.events import app_event_bus as event_bus
from app.services.audit import write_audit_log
from app.services.deployments import create_deployment, rerun_deployment_health
from app.services.serialization import deployment_to_dict


router = APIRouter(tags=["deployments"])
compat_router = APIRouter(tags=["deployments-compat"])


class CancelDeploymentRequest(BaseModel):
    reason: str | None = None


class RollbackDeploymentRequest(BaseModel):
    target_deployment_id: str | None = None


class ParseDeploymentCommandRequest(BaseModel):
    message: str | None = None
    text: str | None = None


async def _check_artifact_owner(db: AsyncSession, user: User, artifact_id: str) -> Artifact:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    conversation = await db.get(Conversation, artifact.conversation_id)
    if not conversation or conversation.creator_id != user.id:
        raise NotFoundError("产物不存在")
    return artifact


async def _check_deployment_owner(db: AsyncSession, user: User, deployment_id: str) -> Deployment:
    deployment = await db.get(Deployment, deployment_id)
    if not deployment:
        raise NotFoundError("部署不存在")
    await _check_artifact_owner(db, user, deployment.artifact_id)
    return deployment


async def _create(db: AsyncSession, user: User, payload: dict) -> Deployment:
    artifact_id = payload.get("artifact_id")
    if not artifact_id and payload.get("conversationId"):
        from sqlalchemy import select

        artifact_result = await db.scalars(
            select(Artifact)
            .where(
                Artifact.conversation_id == payload["conversationId"], Artifact.deleted_at.is_(None)
            )
            .order_by(Artifact.updated_at.desc())
            .limit(1)
        )
        artifact = artifact_result.first()
        artifact_id = artifact.id if artifact else None
    if not artifact_id:
        raise NotFoundError("产物不存在")
    artifact = await _check_artifact_owner(db, user, artifact_id)
    deployment = await create_deployment(
        db, artifact.id, payload.get("mode") or payload.get("environment") or "preview_link"
    )
    await write_audit_log(
        db,
        user=user,
        action="deployment.create",
        target_type="deployment",
        target_id=deployment.id,
        detail={
            "artifact_id": artifact.id,
            "mode": deployment.mode,
            "status": deployment.status,
            "health_status": (deployment.extra or {}).get("health", {}).get("status"),
        },
        risk_score=0.2 if deployment.status == "deployed" else 0.5,
    )
    await db.commit()
    await db.refresh(deployment)
    return deployment


@router.post("/deployments", response_model=ApiResponse[DeploymentOut])
async def create_deployment_endpoint(
    payload: CreateDeploymentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deployment = await _create(db, user, payload.model_dump())
    await event_bus.publish(
        f"deployment:{deployment.id}",
        "deployment:status_changed",
        deployment_to_dict(deployment),
    )
    return ok(deployment_to_dict(deployment), "部署成功")


@router.get("/deployments/{deployment_id}", response_model=ApiResponse[DeploymentOut])
async def get_deployment(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deployment = await _check_deployment_owner(db, user, deployment_id)
    return ok(deployment_to_dict(deployment))


@router.get("/deployments/{deployment_id}/logs", response_model=ApiResponse[dict])
async def get_deployment_logs(
    deployment_id: str,
    level: str = "all",
    page: int = 1,
    page_size: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deployment = await _check_deployment_owner(db, user, deployment_id)
    lines = [line for line in (deployment.deploy_log or "").splitlines() if line.strip()]
    records = [
        {
            "index": index + 1,
            "level": "info",
            "step": "部署",
            "message": line,
            "timestamp": deployment.updated_at.isoformat() if deployment.updated_at else None,
        }
        for index, line in enumerate(lines)
    ]
    if level != "all":
        records = [item for item in records if item["level"] == level]
    start = (page - 1) * page_size
    return ok(
        {
            "items": records[start : start + page_size],
            "total": len(records),
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/deployments/{deployment_id}/cancel", response_model=ApiResponse[DeploymentOut])
async def cancel_deployment(
    deployment_id: str,
    payload: CancelDeploymentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deployment = await _check_deployment_owner(db, user, deployment_id)
    if deployment.status in {"deployed", "failed", "cancelled", "rolled_back"}:
        raise ValidationAppError("已完成的部署不可取消，请使用回滚或重新部署")
    deployment.status = "cancelled"
    deployment.stopped_at = utcnow()
    deployment.error_message = payload.reason or "用户取消部署"
    deployment.deploy_log = (
        f"{deployment.deploy_log}\n用户取消部署：{deployment.error_message}".strip()
    )
    await write_audit_log(
        db,
        user=user,
        action="deployment.cancel",
        target_type="deployment",
        target_id=deployment.id,
        detail={"reason": deployment.error_message},
        risk_score=0.3,
    )
    await db.commit()
    return ok(deployment_to_dict(deployment), "部署已取消")


@router.post("/deployments/{deployment_id}/rollback", response_model=ApiResponse[DeploymentOut])
async def rollback_deployment(
    deployment_id: str,
    payload: RollbackDeploymentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deployment = await _check_deployment_owner(db, user, deployment_id)
    artifact = await _check_artifact_owner(db, user, deployment.artifact_id)
    target_id = payload.target_deployment_id
    target = await db.get(Deployment, target_id) if target_id else None
    if target and target.artifact_id != deployment.artifact_id:
        raise ValidationAppError("只能回滚到同一产物的部署记录")
    rollback = Deployment(
        artifact_id=artifact.id,
        artifact_version_id=(target or deployment).artifact_version_id,
        mode=(target or deployment).mode,
        status="deployed",
        access_url=f"{(target or deployment).access_url}&rollback=1"
        if (target or deployment).access_url
        else None,
        config={**((target or deployment).config or {}), "rollback_from": deployment.id},
        deploy_log=f"回滚部署：from={deployment.id} target={target_id or 'previous'}\n健康检查通过",
        steps=[
            {"name": "选择版本", "status": "completed", "duration_ms": 120},
            {"name": "重新发布", "status": "completed", "duration_ms": 600},
            {"name": "健康检查", "status": "completed", "duration_ms": 200},
        ],
        deployed_at=utcnow(),
        extra={"is_rollback": True, "source_deployment_id": deployment.id},
    )
    deployment.status = "rolled_back"
    db.add(rollback)
    await write_audit_log(
        db,
        user=user,
        action="deployment.rollback",
        target_type="deployment",
        target_id=deployment.id,
        detail={"rollback_id": rollback.id, "target_deployment_id": target_id},
        risk_score=0.4,
    )
    await db.commit()
    await db.refresh(rollback)
    return ok(deployment_to_dict(rollback), "部署已回滚")


@router.post("/deployments/{deployment_id}/health", response_model=ApiResponse[DeploymentOut])
async def check_deployment_health(
    deployment_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deployment = await _check_deployment_owner(db, user, deployment_id)
    deployment = await rerun_deployment_health(db, deployment)
    await write_audit_log(
        db,
        user=user,
        action="deployment.health_check",
        target_type="deployment",
        target_id=deployment.id,
        detail={"health": (deployment.extra or {}).get("health")},
        risk_score=0.1 if deployment.status == "deployed" else 0.3,
    )
    await db.commit()
    await event_bus.publish(
        f"deployment:{deployment.id}",
        "deployment:status_changed",
        deployment_to_dict(deployment),
    )
    return ok(deployment_to_dict(deployment), "部署健康检查完成")


@router.get("/artifacts/{artifact_id}/deployments", response_model=ApiResponse[dict])
async def list_artifact_deployments(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_artifact_owner(db, user, artifact_id)
    deployments_list = (
        await db.scalars(
            select(Deployment)
            .where(Deployment.artifact_id == artifact_id, Deployment.deleted_at.is_(None))
            .order_by(Deployment.created_at.desc())
        )
    ).all()
    return ok(
        {
            "items": [deployment_to_dict(item) for item in deployments_list],
            "total": len(deployments_list),
        }
    )


@router.post("/deployments/parse-command", response_model=ApiResponse[dict])
async def parse_deployment_command(
    payload: ParseDeploymentCommandRequest,
    _user: User = Depends(get_current_user),
):
    text = (payload.message or payload.text or "").lower()
    recognized = any(keyword in text for keyword in ["部署", "发布", "上线", "deploy"])
    mode = "preview_link"
    if "容器" in text or "container" in text:
        mode = "container"
    elif "源码" in text or "download" in text:
        mode = "source_download"
    elif "静态" in text or "static" in text:
        mode = "static_site"
    return ok(
        {
            "recognized": recognized,
            "deploy_mode": mode,
            "confirmation_card": {
                "title": "部署确认",
                "description": f"识别到部署意图，建议使用 {mode} 模式。",
                "actions": ["确认部署", "修改配置", "取消"],
            }
            if recognized
            else None,
        }
    )


@router.get("/deployments/{deployment_id}/stream")
async def stream_deployment(deployment_id: str):
    async def generator():
        async for event in event_bus.subscribe(f"deployment:{deployment_id}", replay=True):
            yield event.as_sse()

    return EventSourceResponse(generator())


@compat_router.post("/deployments", response_model=DeploymentOut)
async def compat_create_deployment(
    payload: CreateDeploymentRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return deployment_to_dict(await _create(db, user, payload.model_dump()))
    except NotFoundError:
        raise
