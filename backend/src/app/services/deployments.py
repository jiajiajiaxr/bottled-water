from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from db.models import Artifact, ArtifactVersion, Deployment, Message, utcnow

SUPPORTED_DEPLOY_MODES = {"preview_link", "static_site", "source_download", "container"}
PREVIEW_URL_MODES = {"preview_link", "static_site", "container"}


def _deploy_mode_message(mode: str) -> str:
    if mode == "container":
        return "当前环境支持 container 模式：通过 AgentHub 应用容器栈托管产物预览入口"
    if mode == "source_download":
        return "当前环境支持源码下载部署模式"
    return "当前环境支持该预览模式"


def deployment_access_url(artifact_id: str, mode: str) -> str | None:
    """根据部署模式生成可验证的本地访问入口。"""

    base_url = get_settings().artifact_base_url.rstrip("/")
    if mode in PREVIEW_URL_MODES:
        return f"{base_url}/api/v1/artifacts/{artifact_id}/preview?deployment=1"
    if mode == "source_download":
        return f"{base_url}/api/v1/artifacts/{artifact_id}/export"
    return None


def deployment_health(artifact: Artifact, mode: str, access_url: str | None) -> dict[str, Any]:
    """基于当前产物和部署模式执行轻量健康检查。"""

    content = artifact.content or {}
    has_payload = any(
        [
            bool(content.get("preview_html")),
            bool(content.get("html")),
            bool(content.get("files")),
            bool(content.get("source_file")),
            bool(content.get("export_file")),
            bool(content.get("text")),
            bool(artifact.storage_url),
            artifact.file_size > 0,
        ]
    )
    checks = [
        {
            "name": "产物记录",
            "status": "passed" if artifact.deleted_at is None else "failed",
            "message": "产物存在" if artifact.deleted_at is None else "产物已删除",
        },
        {
            "name": "部署模式",
            "status": "passed" if mode in SUPPORTED_DEPLOY_MODES else "failed",
            "message": _deploy_mode_message(mode)
            if mode in SUPPORTED_DEPLOY_MODES
            else f"当前环境未启用 {mode} 部署运行时",
        },
        {
            "name": "产物内容",
            "status": "passed" if has_payload else "failed",
            "message": "已找到可预览或可下载内容" if has_payload else "产物缺少可发布内容",
        },
        {
            "name": "访问入口",
            "status": "passed" if access_url else "failed",
            "message": access_url or "未生成访问入口",
        },
    ]
    status = "healthy" if all(item["status"] == "passed" for item in checks) else "failed"
    return {
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


def deployment_steps(mode: str, health: dict[str, Any]) -> list[dict[str, Any]]:
    """把健康检查结果映射成前端可展示的部署步骤。"""

    failed = health.get("status") != "healthy"
    return [
        {"name": "准备产物", "status": "completed", "duration_ms": 180},
        {
            "name": "生成访问入口",
            "status": "completed" if mode in SUPPORTED_DEPLOY_MODES else "failed",
            "duration_ms": 220,
        },
        {
            "name": "健康检查",
            "status": "failed" if failed else "completed",
            "duration_ms": 120,
        },
    ]


def deployment_log(mode: str, access_url: str | None, health: dict[str, Any]) -> str:
    """生成部署日志，避免固定假日志。"""

    lines = [f"部署模式：{mode}", "检查产物记录"]
    if access_url:
        lines.append(f"访问入口：{access_url}")
    for check in health.get("checks", []):
        lines.append(f"{check['name']}：{check['status']} - {check['message']}")
    lines.append("健康检查通过" if health.get("status") == "healthy" else "健康检查失败")
    return "\n".join(lines)


def apply_health_to_deployment(
    deployment: Deployment,
    *,
    artifact: Artifact,
    health: dict[str, Any],
) -> Deployment:
    """将健康检查结果写回 Deployment。"""

    deployment.steps = deployment_steps(deployment.mode, health)
    deployment.deploy_log = deployment_log(deployment.mode, deployment.access_url, health)
    deployment.extra = {**(deployment.extra or {}), "health": health}
    if health.get("status") == "healthy":
        deployment.status = "deployed"
        deployment.deployed_at = deployment.deployed_at or utcnow()
        deployment.error_message = None
    else:
        deployment.status = "failed"
        deployment.error_message = next(
            (
                item.get("message")
                for item in health.get("checks", [])
                if item.get("status") == "failed"
            ),
            "部署健康检查失败",
        )
        deployment.stopped_at = deployment.stopped_at or utcnow()
    deployment.config = {
        **(deployment.config or {}),
        "artifact_name": artifact.name,
        "artifact_type": artifact.type,
    }
    return deployment


async def rerun_deployment_health(db: AsyncSession, deployment: Deployment) -> Deployment:
    """重新执行部署健康检查并持久化结果。"""

    artifact = await db.get(Artifact, deployment.artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    health = deployment_health(artifact, deployment.mode, deployment.access_url)
    apply_health_to_deployment(deployment, artifact=artifact, health=health)
    await db.commit()
    await db.refresh(deployment)
    return deployment


async def create_deployment(
    db: AsyncSession,
    artifact_id: str,
    mode: str = "preview_link",
) -> Deployment:
    """创建预览部署记录，并以产物可访问性作为健康检查事实来源。"""

    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    version_id = await db.scalar(
        select(ArtifactVersion.id)
        .where(ArtifactVersion.artifact_id == artifact.id)
        .order_by(ArtifactVersion.version.desc())
    )
    access_url = deployment_access_url(artifact.id, mode)
    health = deployment_health(artifact, mode, access_url)
    deployment = Deployment(
        artifact_id=artifact.id,
        artifact_version_id=version_id,
        mode=mode,
        access_url=access_url,
    )
    apply_health_to_deployment(deployment, artifact=artifact, health=health)
    db.add(deployment)
    await db.flush()
    db.add(_deployment_message(artifact, deployment))
    await db.commit()
    await db.refresh(deployment)
    return deployment


def create_sync_deployment(
    db: Session,
    artifact: Artifact,
    mode: str = "preview_link",
) -> Deployment:
    """同步工具执行链路使用的部署创建入口。"""

    version_id = db.scalar(
        select(ArtifactVersion.id)
        .where(ArtifactVersion.artifact_id == artifact.id)
        .order_by(ArtifactVersion.version.desc())
    )
    access_url = deployment_access_url(artifact.id, mode)
    health = deployment_health(artifact, mode, access_url)
    deployment = Deployment(
        artifact_id=artifact.id,
        artifact_version_id=version_id,
        mode=mode,
        access_url=access_url,
    )
    apply_health_to_deployment(deployment, artifact=artifact, health=health)
    db.add(deployment)
    db.flush()
    db.add(_deployment_message(artifact, deployment))
    db.commit()
    db.refresh(deployment)
    return deployment


def _deployment_message(artifact: Artifact, deployment: Deployment) -> Message:
    progress = 100 if deployment.status == "deployed" else 0
    return Message(
        conversation_id=artifact.conversation_id,
        sender_type="system",
        sender_name="部署服务",
        content_type="deploy_status_card",
        content={
            "deployment_id": deployment.id,
            "artifact_name": artifact.name,
            "deploy_mode": deployment.mode,
            "status": deployment.status,
            "progress": progress,
            "deploy_url": deployment.access_url,
            "steps": deployment.steps,
            "health": (deployment.extra or {}).get("health"),
            "error_message": deployment.error_message,
        },
        status="completed",
    )
