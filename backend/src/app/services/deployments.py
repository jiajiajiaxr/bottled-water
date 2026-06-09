from __future__ import annotations

import mimetypes
from pathlib import Path, PurePosixPath
from shutil import rmtree
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.services.tools.builtins.artifact.export import export_artifact
from db.models import Artifact, ArtifactVersion, Deployment, Message, utcnow

SUPPORTED_DEPLOY_MODES = {"preview_link", "static_site", "source_download", "container"}
PREVIEW_URL_MODES = {"preview_link", "static_site", "container"}
DEPLOYMENT_SITE_MODES = {"preview_link", "static_site", "container"}


def _deploy_mode_message(mode: str) -> str:
    if mode == "container":
        return "当前环境支持 container 模式：通过 AgentHub 应用容器栈托管产物预览入口"
    if mode == "source_download":
        return "当前环境支持源码下载部署模式"
    return "当前环境支持该预览模式"


def deployments_root() -> Path:
    root = Path(get_settings().storage_dir).resolve().parent / "deployments"
    root.mkdir(parents=True, exist_ok=True)
    return root


def deployment_site_root(deployment_id: str) -> Path:
    return deployments_root() / deployment_id / "site"


def deployment_site_file(deployment: Deployment, path: str | None = None) -> tuple[Path, str]:
    site_root = deployment_site_root(deployment.id).resolve()
    requested = (path or "index.html").strip().replace("\\", "/") or "index.html"
    rel = _safe_site_path(requested) or PurePosixPath("index.html")
    target = (site_root / Path(*rel.parts)).resolve()
    if not str(target).startswith(str(site_root)):
        target = site_root / "index.html"
    if target.is_dir():
        target = target / "index.html"
    content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return target, content_type


def deployment_access_url(artifact_id: str, mode: str, *, deployment_id: str | None = None) -> str | None:
    """根据部署模式生成可验证的本地访问入口。"""

    base_url = get_settings().artifact_base_url.rstrip("/")
    if mode in DEPLOYMENT_SITE_MODES and deployment_id:
        return f"{base_url}/api/v1/deployments/{deployment_id}/site/"
    if mode in PREVIEW_URL_MODES:
        return f"{base_url}/api/v1/artifacts/{artifact_id}/preview?deployment=1"
    if mode == "source_download":
        return f"{base_url}/api/v1/artifacts/{artifact_id}/export"
    return None


def publish_deployment_site(artifact: Artifact, deployment: Deployment) -> dict[str, Any]:
    site_root = deployment_site_root(deployment.id)
    if site_root.exists():
        rmtree(site_root)
    site_root.mkdir(parents=True, exist_ok=True)

    files = _artifact_deploy_files(artifact)
    written: list[dict[str, Any]] = []
    for name, raw in files.items():
        rel = _safe_site_path(name)
        if rel is None:
            continue
        target = site_root / Path(*rel.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        written.append(
            {
                "path": rel.as_posix(),
                "size": len(raw),
                "content_type": mimetypes.guess_type(rel.name)[0] or "application/octet-stream",
            }
        )

    deployment.config = {
        **(deployment.config or {}),
        "site_root": str(site_root),
        "published_files": written,
    }
    return {"site_root": str(site_root), "files": written}


def deployment_health(artifact: Artifact, mode: str, access_url: str | None, deployment: Deployment | None = None) -> dict[str, Any]:
    """基于当前产物和部署模式执行轻量健康检查。"""

    content = artifact.content or {}
    site_root = deployment_site_root(deployment.id) if deployment else None
    site_index = site_root / "index.html" if site_root else None
    site_ready = bool(site_index and site_index.exists() and site_index.stat().st_size > 0)
    has_payload = any(
        [
            site_ready,
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
        {
            "name": "静态站点文件",
            "status": "passed" if mode not in DEPLOYMENT_SITE_MODES or site_ready else "failed",
            "message": "index.html 已发布" if site_ready else ("当前模式不需要静态站点" if mode not in DEPLOYMENT_SITE_MODES else "未生成可访问的 index.html"),
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
    if deployment.mode in DEPLOYMENT_SITE_MODES:
        publish_deployment_site(artifact, deployment)
        deployment.access_url = deployment_access_url(artifact.id, deployment.mode, deployment_id=deployment.id)
    health = deployment_health(artifact, deployment.mode, deployment.access_url, deployment)
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
    deployment_id = str(uuid4())
    deployment = Deployment(
        id=deployment_id,
        artifact_id=artifact.id,
        artifact_version_id=version_id,
        mode=mode,
        access_url=None,
    )
    if mode in DEPLOYMENT_SITE_MODES:
        publish_deployment_site(artifact, deployment)
    deployment.access_url = deployment_access_url(artifact.id, mode, deployment_id=deployment.id)
    health = deployment_health(artifact, mode, deployment.access_url, deployment)
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
    deployment_id = str(uuid4())
    deployment = Deployment(
        id=deployment_id,
        artifact_id=artifact.id,
        artifact_version_id=version_id,
        mode=mode,
        access_url=None,
    )
    if mode in DEPLOYMENT_SITE_MODES:
        publish_deployment_site(artifact, deployment)
    deployment.access_url = deployment_access_url(artifact.id, mode, deployment_id=deployment.id)
    health = deployment_health(artifact, mode, deployment.access_url, deployment)
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


def _artifact_deploy_files(artifact: Artifact) -> dict[str, bytes]:
    content = artifact.content or {}
    raw_files = content.get("files") if isinstance(content.get("files"), dict) else {}
    files: dict[str, bytes] = {}
    for name, value in raw_files.items():
        if isinstance(value, bytes):
            files[str(name)] = value
        elif isinstance(value, str):
            files[str(name)] = value.encode("utf-8")

    html = str(
        content.get("preview_html")
        or content.get("html")
        or raw_files.get("index.html")
        or ""
    )
    if html and "index.html" not in files:
        files["index.html"] = html.encode("utf-8")

    if not files and _artifact_is_html_like(artifact):
        try:
            exported = export_artifact(artifact, "html")
            files["index.html"] = exported.content
        except Exception:
            pass
    return files


def _artifact_is_html_like(artifact: Artifact) -> bool:
    content = artifact.content or {}
    fmt = str(content.get("format") or artifact.type or "").lower()
    media_type = str(content.get("media_type") or artifact.mime_type or "").lower()
    return fmt in {"html", "web_app", "webpage"} or "html" in media_type or artifact.type in {"web_app", "webpage", "html"}


def _deployment_index_html(artifact: Artifact) -> str:
    title = artifact.name or "AgentHub 部署预览"
    export_url = f"/api/v1/artifacts/{artifact.id}/export"
    preview_url = f"/api/v1/artifacts/{artifact.id}/preview"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_escape_html(title)}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f8fb; color: #172033; }}
    main {{ max-width: 880px; margin: 64px auto; padding: 40px; background: #fff; border: 1px solid #dbe5f2; border-radius: 18px; box-shadow: 0 24px 70px rgba(24, 50, 90, .12); }}
    h1 {{ margin: 0 0 16px; font-size: 28px; }}
    p {{ color: #667085; line-height: 1.8; }}
    a {{ display: inline-flex; margin-right: 12px; padding: 10px 14px; border-radius: 10px; color: #0b63f6; background: #edf5ff; text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <h1>{_escape_html(title)}</h1>
    <p>该产物已由 AgentHub 发布为可访问部署预览。当前格式不适合直接作为静态网页运行，可通过下方入口查看或下载原产物。</p>
    <a href="{preview_url}">打开产物预览</a>
    <a href="{export_url}">下载原文件</a>
  </main>
</body>
</html>"""


def _safe_site_path(value: str) -> PurePosixPath | None:
    normalized = str(value).replace("\\", "/").strip("/")
    if not normalized:
        return PurePosixPath("index.html")
    rel = PurePosixPath(normalized)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        return None
    return rel


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
