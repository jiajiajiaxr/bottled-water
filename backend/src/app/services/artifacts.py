from __future__ import annotations

import difflib
import html as html_lib
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.services.tools.builtins.artifact.storage import regenerate_binary_from_preview
from db.models import Artifact, ArtifactVersion, Conversation, Deployment, Message, Task, utcnow


def classify_artifact_request(prompt: str) -> str | None:
    text = prompt.lower()
    groups: list[tuple[str, tuple[str, ...]]] = [
        ("document", ("word", "docx", "pdf", "文档", "报告", "方案", "合同", "说明书", "prd", "需求文档", "简历", "计划书")),
        ("spreadsheet", ("excel", "xlsx", "表格", "清单", "台账", "预算", "排期表", "csv")),
        ("slides", ("ppt", "pptx", "slide", "slides", "幻灯片", "演示文稿", "答辩稿", "汇报")),
        ("web_app", ("页面", "网页", "网站", "web", "html", "react", "前端", "dashboard", "看板", "app", "预览", "部署")),
        ("code", ("代码", "脚本", "api", "接口", "程序", "组件", "项目")),
    ]
    for artifact_type, keywords in groups:
        if any(keyword in text for keyword in keywords):
            return artifact_type
    return None


def build_demo_html(prompt: str, review: str = "", artifact_type: str = "web_app") -> str:
    escaped_prompt = html_lib.escape(prompt[:240] or "多 Agent 协作产物")
    escaped_review = html_lib.escape(review[:160] or "审查通过，结构清晰")
    templates = {
        "document": (
            "Word 文档预览",
            "生成了一份可继续编辑的结构化文档",
            f"""
            <article class="doc-page">
              <h1>{escaped_prompt}</h1>
              <p class="lead">本文档由 AgentHub 多 Agent 协作生成，适合导出为 Word/PDF 或继续在线修订。</p>
              <h2>一、目标</h2><p>围绕用户输入形成清晰目标、范围和验收标准。</p>
              <h2>二、正文结构</h2><ul><li>背景与问题</li><li>方案设计</li><li>实施计划</li><li>风险与审查结论</li></ul>
              <h2>三、Reviewer 结论</h2><p>{escaped_review}</p>
            </article>
            """,
        ),
        "spreadsheet": (
            "表格产物预览",
            "生成了可导出为 Excel/CSV 的表格结构",
            f"""
            <section class="sheet">
              <h1>{escaped_prompt}</h1>
              <table><thead><tr><th>编号</th><th>事项</th><th>负责人</th><th>状态</th><th>验收</th></tr></thead>
              <tbody>
                <tr><td>1</td><td>需求拆解</td><td>Master Agent</td><td>完成</td><td>任务边界清晰</td></tr>
                <tr><td>2</td><td>内容生成</td><td>Worker Agent</td><td>完成</td><td>字段齐全</td></tr>
                <tr><td>3</td><td>质量审查</td><td>Reviewer</td><td>通过</td><td>{escaped_review}</td></tr>
              </tbody></table>
            </section>
            """,
        ),
        "slides": (
            "演示文稿预览",
            "生成了适合答辩展示的幻灯片大纲",
            f"""
            <section class="slides">
              <article><span>01</span><h1>{escaped_prompt}</h1><p>目标与背景</p></article>
              <article><span>02</span><h2>方案架构</h2><p>Master 调度、Worker 执行、Reviewer 门禁。</p></article>
              <article><span>03</span><h2>验证结果</h2><p>{escaped_review}</p></article>
            </section>
            """,
        ),
        "code": (
            "代码产物预览",
            "生成了代码/接口交付说明",
            f"""
            <section class="code-doc">
              <h1>{escaped_prompt}</h1>
              <pre><code>def agenthub_delivery():\n    plan = master_agent.plan()\n    result = workers.execute(plan)\n    return reviewer.approve(result)</code></pre>
              <p>{escaped_review}</p>
            </section>
            """,
        ),
    }
    title, subtitle, body = templates.get(
        artifact_type,
        (
            "AgentHub 交付预览",
            "生成了可预览、编辑、Diff 和部署的 Web 产物",
            f"""
            <section class="agenthub-demo">
              <div class="hero">
                <span class="eyebrow">Multi-Agent Delivery</span>
                <h1>AgentHub 交付预览</h1>
                <p>{escaped_prompt}</p>
                <div class="grid">
                  <article><strong>Master</strong><span>需求拆解与调度计划已生成</span></article>
                  <article><strong>Workers</strong><span>前端、后端、部署并行执行</span></article>
                  <article><strong>Reviewer</strong><span>{escaped_review}</span></article>
                </div>
                <button onclick="document.body.classList.toggle('done')">切换演示状态</button>
              </div>
            </section>
            """,
        ),
    )
    title = html_lib.escape(title)
    subtitle = html_lib.escape(subtitle)
    return f"""<section class="agenthub-demo">
  <header class="top"><span class="eyebrow">AgentHub Artifact</span><h1>{title}</h1><p>{subtitle}</p></header>
  {body}
</section>
<style>
  body {{ margin: 0; font-family: Inter, system-ui, sans-serif; background: #f5f7fb; color: #1d2433; }}
  .agenthub-demo {{ min-height: 100vh; padding: 32px; box-sizing: border-box; }}
  .top {{ max-width: 920px; margin: 0 auto 22px; }}
  .hero {{ width: min(760px, 100%); background: #fff; border: 1px solid #dde5f2; border-radius: 8px; padding: 34px; box-shadow: 0 20px 70px rgba(31, 45, 61, .12); }}
  .eyebrow {{ color: #1677ff; font-weight: 800; font-size: 12px; text-transform: uppercase; }}
  h1 {{ margin: 10px 0; font-size: 42px; line-height: 1.05; }}
  h2 {{ margin: 24px 0 8px; }}
  p {{ color: #526071; line-height: 1.7; }}
  .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 24px 0; }}
  article {{ border: 1px solid #e4ebf5; padding: 16px; border-radius: 8px; background: #fbfdff; }}
  article span {{ display: block; margin-top: 8px; color: #627084; font-size: 13px; }}
  .doc-page, .sheet, .code-doc {{ max-width: 920px; margin: 0 auto; background: #fff; border: 1px solid #dde5f2; border-radius: 8px; padding: 34px; box-shadow: 0 18px 54px rgba(31,45,61,.10); }}
  .lead {{ font-size: 18px; }}
  table {{ width: 100%; border-collapse: collapse; background: white; }}
  th, td {{ border: 1px solid #dbe3ef; padding: 12px; text-align: left; }}
  th {{ background: #eef6ff; }}
  .slides {{ max-width: 960px; margin: 0 auto; display: grid; gap: 18px; }}
  .slides article {{ min-height: 220px; display: flex; flex-direction: column; justify-content: center; }}
  pre {{ overflow: auto; padding: 18px; background: #0f172a; color: #e2e8f0; border-radius: 8px; }}
  button {{ border: 0; background: #1677ff; color: white; padding: 11px 16px; border-radius: 8px; font-weight: 700; }}
  body.done .hero {{ outline: 5px solid rgba(22, 119, 255, .16); }}
  @media (max-width: 680px) {{ .grid {{ grid-template-columns: 1fr; }} h1 {{ font-size: 30px; }} }}
</style>"""


async def create_artifact(
    db: AsyncSession,
    conversation: Conversation,
    *,
    task: Task | None,
    name: str,
    html: str,
    agent_id: str | None = None,
    artifact_type: str = "web_app",
    description: str | None = None,
) -> Artifact:
    previous_html = html.replace("AgentHub Artifact", "AgentHub Artifact v0")
    artifact = Artifact(
        conversation_id=conversation.id,
        task_id=task.id if task else None,
        agent_id=agent_id,
        type=artifact_type,
        name=name,
        description=description or "由多 Agent 协作生成的可预览产物。",
        status="published",
        storage_url="/api/v1/artifacts/preview-pending",
        content={
            "files": {"index.html": html},
            "previous_files": {"index.html": previous_html},
            "summary": "包含响应式页面、交互按钮和部署入口。",
        },
        current_version=1,
        mime_type="text/html",
    )
    db.add(artifact)
    await db.flush()
    artifact.storage_url = f"{get_settings().artifact_base_url}/api/v1/artifacts/{artifact.id}/preview"
    db.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            version=1,
            content=artifact.content,
            change_summary="初始 Agent 产物",
        )
    )
    await db.flush()
    return artifact


async def create_preview_message(db: AsyncSession, conversation: Conversation, artifact: Artifact) -> Message:
    message = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=artifact.agent_id,
        sender_name="Master Agent",
        content_type="preview_card",
        content={
            "artifact_id": artifact.id,
            "title": artifact.name,
            "artifact_type": artifact.type,
            "preview_url": f"/api/v1/artifacts/{artifact.id}/preview",
            "file_count": len(artifact.content.get("files") or {}),
            "total_size": len((artifact.content.get("files") or {}).get("index.html", "")),
        },
        status="completed",
    )
    db.add(message)
    return message


def compute_artifact_diff(old: str, new: str) -> list[dict[str, Any]]:
    diff = difflib.ndiff(old.splitlines(), new.splitlines())
    entries: list[dict[str, Any]] = []
    old_line = 0
    new_line = 0
    for line in diff:
        marker = line[:2]
        text = line[2:]
        if marker == "  ":
            old_line += 1
            new_line += 1
            continue
        if marker == "- ":
            old_line += 1
            entries.append({"type": "remove", "line": old_line, "content": text})
        elif marker == "+ ":
            new_line += 1
            entries.append({"type": "add", "line": new_line, "content": text})
    return entries


def update_artifact_files(
    db: AsyncSession | Session,
    artifact_id: str,
    files: dict[str, str],
    summary: str,
):
    if isinstance(db, AsyncSession):
        return _update_artifact_files_async(db, artifact_id, files, summary)
    return _update_artifact_files_sync(db, artifact_id, files, summary)


def _update_artifact_files_sync(
    db: Session,
    artifact_id: str,
    files: dict[str, str],
    summary: str,
) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    current_content = artifact.content or {}
    current_files = current_content.get("files") or {}
    next_version = artifact.current_version + 1
    artifact.content, checksum = _build_versioned_artifact_content(
        db,
        artifact,
        current_content=current_content,
        previous_files=current_files,
        files=files,
        summary=summary,
        next_version=next_version,
    )
    artifact.current_version = next_version
    artifact.updated_at = utcnow()
    db.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            version=next_version,
            content=artifact.content,
            change_summary=summary,
            checksum=checksum,
        )
    )
    db.commit()
    db.refresh(artifact)
    return artifact


async def _update_artifact_files_async(
    db: AsyncSession,
    artifact_id: str,
    files: dict[str, str],
    summary: str,
) -> Artifact:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    current_content = artifact.content or {}
    current_files = current_content.get("files") or {}
    next_version = artifact.current_version + 1
    artifact.content, checksum = await db.run_sync(
        lambda session: _build_versioned_artifact_content(
            session,
            artifact,
            current_content=current_content,
            previous_files=current_files,
            files=files,
            summary=summary,
            next_version=next_version,
        )
    )
    artifact.current_version = next_version
    artifact.updated_at = utcnow()
    db.add(
        ArtifactVersion(
            artifact_id=artifact.id,
            version=next_version,
            content=artifact.content,
            change_summary=summary,
            checksum=checksum,
        )
    )
    await db.commit()
    await db.refresh(artifact)
    return artifact


def _build_versioned_artifact_content(
    db: Session,
    artifact: Artifact,
    *,
    current_content: dict[str, Any],
    previous_files: dict[str, str],
    files: dict[str, str],
    summary: str,
    next_version: int,
) -> tuple[dict[str, Any], str]:
    content = {
        **current_content,
        "previous_files": previous_files,
        "files": files,
        "summary": summary,
    }
    preview_html = files.get("index.html") or current_content.get("preview_html") or ""
    if preview_html:
        content["preview_html"] = preview_html

    descriptor = _regenerate_or_copy_source_file(
        db,
        artifact,
        current_content=current_content,
        preview_html=preview_html,
        next_version=next_version,
    )
    if descriptor:
        content.update(descriptor)
        checksum = descriptor["source_file"].get("checksum") or _checksum_from_files(files)
        return content, checksum

    return content, _checksum_from_files(files)


def _regenerate_or_copy_source_file(
    db: Session,
    artifact: Artifact,
    *,
    current_content: dict[str, Any],
    preview_html: str,
    next_version: int,
) -> dict[str, Any] | None:
    source_file = current_content.get("source_file")
    if not isinstance(source_file, dict):
        return None

    format_name = (
        current_content.get("format")
        or source_file.get("format")
        or Path(str(source_file.get("filename") or "")).suffix.lstrip(".")
    )
    owner_id = _artifact_owner_id(db, artifact)
    if owner_id and format_name and preview_html:
        try:
            return regenerate_binary_from_preview(
                db,
                owner_id=owner_id,
                artifact=artifact,
                format_name=str(format_name),
                preview_html=preview_html,
                version=next_version,
            )
        except Exception:
            pass

    copied = dict(source_file)
    copied["version"] = next_version
    checksum = _checksum_from_file(copied.get("storage_path")) or copied.get("checksum") or _checksum_from_files({})
    copied["checksum"] = checksum
    export_file = dict(current_content.get("export_file") or copied)
    export_file.update({"version": next_version, "checksum": checksum})
    return {
        "source_file": copied,
        "export_file": export_file,
        "filename": copied.get("filename") or current_content.get("filename"),
        "media_type": copied.get("media_type") or current_content.get("media_type"),
        "file_size": copied.get("size") or current_content.get("file_size") or 0,
    }


def _artifact_owner_id(db: Session, artifact: Artifact) -> str | None:
    conversation = db.get(Conversation, artifact.conversation_id)
    return conversation.creator_id if conversation else None


def _checksum_from_file(path: Any) -> str | None:
    if not path:
        return None
    try:
        file_path = Path(str(path))
        if file_path.exists() and file_path.is_file():
            return hashlib.sha256(file_path.read_bytes()).hexdigest()
    except OSError:
        return None
    return None


def _checksum_from_files(files: dict[str, Any]) -> str:
    raw = json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


async def create_deployment(db: AsyncSession, artifact_id: str, mode: str = "preview_link") -> Deployment:
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    deployment = Deployment(
        artifact_id=artifact.id,
        artifact_version_id=await db.scalar(
            select(ArtifactVersion.id)
            .where(ArtifactVersion.artifact_id == artifact.id)
            .order_by(ArtifactVersion.version.desc())
        ),
        mode=mode,
        status="deployed",
        access_url=f"{get_settings().artifact_base_url}/api/v1/artifacts/{artifact.id}/preview?deployment=1",
        deploy_log=(
            "准备部署环境\n"
            "写入静态文件\n"
            "生成预览访问地址\n"
            "健康检查通过"
        ),
        steps=[
            {"name": "准备", "status": "completed", "duration_ms": 400},
            {"name": "构建", "status": "completed", "duration_ms": 1200},
            {"name": "发布", "status": "completed", "duration_ms": 600},
        ],
        deployed_at=utcnow(),
    )
    db.add(deployment)
    await db.flush()
    db.add(
        Message(
            conversation_id=artifact.conversation_id,
            sender_type="agent",
            sender_name="Deploy Agent",
            content_type="deploy_status_card",
            content={
                "deployment_id": deployment.id,
                "artifact_name": artifact.name,
                "deploy_mode": deployment.mode,
                "status": deployment.status,
                "progress": 100,
                "deploy_url": deployment.access_url,
                "steps": deployment.steps,
            },
            status="completed",
        )
    )
    await db.commit()
    await db.refresh(deployment)
    return deployment
