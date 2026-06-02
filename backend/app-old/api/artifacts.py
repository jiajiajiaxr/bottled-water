from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.errors import NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from app.models import Artifact, Conversation, FileAsset, KnowledgeBase, User, utcnow
from app.services.artifacts import (
    build_demo_html,
    compute_artifact_diff,
    create_artifact,
    update_artifact_files,
)
from app.services.tools.builtins.artifact.export import default_export_format, export_artifact
from app.services.audit import write_audit_log
from app.schemas.requests import CreateKnowledgeBaseRequest, ImportKnowledgeTextRequest, RetrieveKnowledgeRequest
from app.services.files import attachment_path, ensure_extension_tables, save_upload
from app.services.files.previewers.office import build_office_preview, is_office_file
from app.services.knowledge import index_document, retrieve
from app.services.serialization import (
    artifact_to_dict,
    file_asset_to_dict,
    knowledge_base_to_dict,
    knowledge_document_to_dict,
)


router = APIRouter(tags=["artifacts"])
compat_router = APIRouter(tags=["artifacts-compat"])


async def _payload(request: Request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _owned_artifact(db: Session, user: User, artifact_id: str) -> Artifact:
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    conversation = db.get(Conversation, artifact.conversation_id)
    if not conversation or conversation.creator_id != user.id:
        raise NotFoundError("产物不存在")
    return artifact


def _attachment_headers(filename: str) -> dict[str, str]:
    safe_filename = filename.replace("\\", "_").replace("/", "_").replace('"', "")
    ascii_filename = safe_filename.encode("ascii", "ignore").decode().strip() or "agenthub-artifact"
    encoded_filename = quote(safe_filename)
    return {
        "Content-Disposition": (
            f'attachment; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}'
        )
    }


def _owned_file(db: Session, user: User, file_id: str) -> FileAsset:
    ensure_extension_tables(db)
    file_asset = db.get(FileAsset, file_id)
    if not file_asset or file_asset.owner_id != user.id or file_asset.deleted_at is not None:
        raise NotFoundError("文件不存在")
    return file_asset


def _artifact_workspace_id(db: Session, artifact: Artifact) -> str:
    conversation = db.get(Conversation, artifact.conversation_id)
    if conversation and isinstance(conversation.extra, dict):
        value = conversation.extra.get("workspace_id") or conversation.extra.get("workspaceId")
        if value:
            return str(value)
    return artifact.conversation_id or artifact.id


def _owned_kb(db: Session, user: User, knowledge_base_id: str) -> KnowledgeBase:
    ensure_extension_tables(db)
    kb = db.scalar(
        select(KnowledgeBase)
        .options(selectinload(KnowledgeBase.documents))
        .where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.owner_id == user.id,
            KnowledgeBase.deleted_at.is_(None),
        )
    )
    if not kb:
        raise NotFoundError("知识库不存在")
    return kb


def _latest_for_conversation(db: Session, user: User, conversation_id: str) -> Artifact:
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.creator_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    artifact = db.scalar(
        select(Artifact)
        .where(Artifact.conversation_id == conversation.id, Artifact.deleted_at.is_(None))
        .order_by(Artifact.updated_at.desc())
    )
    if not artifact:
        raise NotFoundError("当前会话暂无产物")
    return artifact


def _create_from_payload(db: Session, user: User, payload: dict) -> Artifact:
    conversation_id = payload.get("conversation_id")
    if not conversation_id:
        raise ValidationAppError("conversation_id 不能为空")
    conversation = db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.creator_id == user.id)
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    content = payload.get("content") or {}
    html = content.get("html") or (content.get("files") or {}).get("index.html")
    if not html:
        html = build_demo_html(payload.get("title") or "Acceptance Preview")
    artifact = create_artifact(
        db,
        conversation,
        task=None,
        name=payload.get("title") or payload.get("name") or "预览产物",
        html=html,
    )
    db.commit()
    db.refresh(artifact)
    return artifact


@router.get("/conversations/{conversation_id}/artifacts")
async def list_conversation_artifacts(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        artifact = _latest_for_conversation(db, user, conversation_id)
    except NotFoundError:
        return ok([])
    return ok([artifact_to_dict(artifact)])


@router.get("/conversations/{conversation_id}/artifact")
async def get_conversation_artifact(
    conversation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(artifact_to_dict(_latest_for_conversation(db, user, conversation_id)))


@router.post("/artifacts")
async def create_artifact_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(artifact_to_dict(_create_from_payload(db, user, await _payload(request))), "产物已创建")


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(artifact_to_dict(_owned_artifact(db, user, artifact_id)))


@router.get("/artifacts/{artifact_id}/content")
async def get_artifact_content(
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = _owned_artifact(db, user, artifact_id)
    return ok(artifact.content)


@router.get("/artifacts/{artifact_id}/exports")
async def list_artifact_exports(
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = _owned_artifact(db, user, artifact_id)
    default_format = default_export_format(artifact)
    return ok(
        {
            "artifact_id": artifact.id,
            "default_format": default_format,
            "formats": [
                {"format": default_format, "url": f"/api/v1/artifacts/{artifact.id}/export?format={default_format}"}
            ],
        }
    )


@router.get("/artifacts/{artifact_id}/export")
async def download_artifact_export(
    artifact_id: str,
    request: Request,
    format: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = _owned_artifact(db, user, artifact_id)
    try:
        exported = export_artifact(artifact, format)
    except ValueError as exc:
        raise ValidationAppError(str(exc)) from exc
    write_audit_log(
        db,
        user=user,
        action="artifact.export",
        target_type="artifact",
        target_id=artifact.id,
        detail={"format": format or default_export_format(artifact), "filename": exported.filename},
        request=request,
        risk_score=0.1,
    )
    db.commit()
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers=_attachment_headers(exported.filename),
    )


@router.get("/artifacts/{artifact_id}/preview-pdf")
async def download_artifact_preview_pdf(
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = _owned_artifact(db, user, artifact_id)
    exported = export_artifact(artifact, default_export_format(artifact))
    if not is_office_file(exported.media_type, exported.filename):
        if exported.media_type == "application/pdf" or exported.filename.lower().endswith(".pdf"):
            return Response(content=exported.content, media_type="application/pdf")
        raise ValidationAppError("当前产物不是可转换的 Office 文件")
    result = build_office_preview(
        workspace_id=_artifact_workspace_id(db, artifact),
        node_id=f"artifact:{artifact.id}",
        target={
            "kind": "artifact",
            "artifact": artifact,
            "artifact_id": artifact.id,
            "artifact_type": artifact.type,
            "bytes": exported.content,
            "filename": exported.filename,
            "mime_type": exported.media_type,
        },
        filename=exported.filename,
        mime_type=exported.media_type,
    )
    if not result.preview_pdf_path:
        raise ValidationAppError(result.error or "Office PDF 预览生成失败")
    return FileResponse(
        str(result.preview_pdf_path),
        media_type="application/pdf",
        filename=f"{artifact.name}.preview.pdf",
    )


@router.put("/artifacts/{artifact_id}")
@router.post("/artifacts/{artifact_id}/versions")
async def save_artifact(
    artifact_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_artifact(db, user, artifact_id)
    payload = await _payload(request)
    files = payload.get("files")
    if not files and payload.get("code"):
        files = {"index.html": payload["code"]}
    if not files and payload.get("content", {}).get("files"):
        files = payload["content"]["files"]
    if not files:
        raise ValidationAppError("产物文件不能为空")
    artifact = update_artifact_files(db, artifact_id, files, payload.get("change_summary") or "在线编辑保存")
    return ok(artifact_to_dict(artifact), "产物已保存")


@router.post("/artifacts/{artifact_id}/diff")
async def artifact_diff(
    artifact_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = _owned_artifact(db, user, artifact_id)
    files = artifact.content.get("files") or {}
    previous = artifact.content.get("previous_files") or {}
    old = previous.get("index.html") or ""
    new = files.get("index.html") or ""
    changes = compute_artifact_diff(old, new)
    return ok(
        {
            "artifact_id": artifact.id,
            "old_version": max(1, artifact.current_version - 1),
            "new_version": artifact.current_version,
            "diff_entries": [{"file_path": "index.html", "changes": changes}],
            "summary": {
                "additions": len([item for item in changes if item["type"] == "add"]),
                "deletions": len([item for item in changes if item["type"] == "remove"]),
                "files_changed": 1,
            },
        }
    )


@router.post("/files")
@router.post("/attachments")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
    purpose: str = "attachment",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if conversation_id:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.creator_id == user.id,
                Conversation.deleted_at.is_(None),
            )
        )
        if not conversation:
            raise NotFoundError("会话不存在")
    file_asset = await save_upload(
        db,
        user=user,
        upload=file,
        conversation_id=conversation_id,
        purpose=purpose,
    )
    return ok(file_asset_to_dict(file_asset), "文件已上传")


@router.get("/files")
@router.get("/attachments")
async def list_files(
    conversation_id: str | None = None,
    purpose: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_extension_tables(db)
    query = select(FileAsset).where(FileAsset.owner_id == user.id, FileAsset.deleted_at.is_(None))
    if conversation_id:
        query = query.where(FileAsset.conversation_id == conversation_id)
    if purpose:
        query = query.where(FileAsset.purpose == purpose)
    items = db.scalars(query.order_by(FileAsset.created_at.desc())).all()
    return ok({"items": [file_asset_to_dict(item) for item in items], "total": len(items)})


@router.get("/files/{file_id}")
@router.get("/attachments/{file_id}")
async def get_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(file_asset_to_dict(_owned_file(db, user, file_id)))


@router.get("/files/{file_id}/download")
@router.get("/attachments/{file_id}/download")
async def download_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_asset = _owned_file(db, user, file_id)
    return FileResponse(
        attachment_path(file_asset),
        media_type=file_asset.content_type,
        filename=file_asset.original_filename,
    )


@router.delete("/files/{file_id}")
@router.delete("/attachments/{file_id}")
async def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_asset = _owned_file(db, user, file_id)
    file_asset.deleted_at = utcnow()
    file_asset.parse_status = "deleted"
    db.commit()
    return ok({"id": file_asset.id, "deleted": True})


@router.get("/knowledge-bases")
async def list_knowledge_bases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_extension_tables(db)
    items = db.scalars(
        select(KnowledgeBase)
        .options(selectinload(KnowledgeBase.documents))
        .where(KnowledgeBase.owner_id == user.id, KnowledgeBase.deleted_at.is_(None))
        .order_by(KnowledgeBase.updated_at.desc())
    ).all()
    return ok({"items": [knowledge_base_to_dict(item) for item in items], "total": len(items)})


@router.post("/knowledge-bases")
async def create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_extension_tables(db)
    kb = KnowledgeBase(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        visibility=payload.visibility,
        config=payload.config,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return ok(knowledge_base_to_dict(kb), "知识库已创建")


@router.get("/knowledge-bases/{knowledge_base_id}")
async def get_knowledge_base(
    knowledge_base_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(knowledge_base_to_dict(_owned_kb(db, user, knowledge_base_id)))


@router.post("/knowledge-bases/{knowledge_base_id}/documents")
async def import_knowledge_text(
    knowledge_base_id: str,
    payload: ImportKnowledgeTextRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = _owned_kb(db, user, knowledge_base_id)
    document = index_document(
        db,
        kb,
        title=payload.title,
        content=payload.content,
        source_type=payload.source_type,
        source_uri=payload.source_uri,
    )
    db.commit()
    db.refresh(document)
    db.refresh(kb)
    return ok(knowledge_document_to_dict(document), "文档已索引")


@router.post("/knowledge-bases/{knowledge_base_id}/documents/upload")
async def upload_knowledge_document(
    knowledge_base_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = _owned_kb(db, user, knowledge_base_id)
    file_asset = await save_upload(db, user=user, upload=file, purpose="knowledge")
    content = file_asset.extracted_text or f"{file_asset.original_filename} ({file_asset.content_type})"
    document = index_document(
        db,
        kb,
        title=file_asset.original_filename,
        content=content,
        source_type="upload",
        source_uri=file_asset.public_url or f"/api/v1/files/{file_asset.id}/download",
        file_asset_id=file_asset.id,
    )
    db.commit()
    db.refresh(document)
    return ok(
        {"file": file_asset_to_dict(file_asset), "document": knowledge_document_to_dict(document)},
        "文档已上传并索引",
    )


@router.get("/knowledge-bases/{knowledge_base_id}/documents")
async def list_knowledge_documents(
    knowledge_base_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = _owned_kb(db, user, knowledge_base_id)
    documents = [item for item in kb.documents if item.deleted_at is None]
    return ok({"items": [knowledge_document_to_dict(item) for item in documents], "total": len(documents)})


@router.post("/knowledge-bases/{knowledge_base_id}/retrieve")
async def retrieve_knowledge(
    knowledge_base_id: str,
    payload: RetrieveKnowledgeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = _owned_kb(db, user, knowledge_base_id)
    results = retrieve(
        db,
        kb,
        query=payload.query,
        top_k=payload.top_k,
        threshold=payload.similarity_threshold,
    )
    return ok({"items": results, "total": len(results), "mode": payload.mode})


@router.get("/artifacts/{artifact_id}/preview")
async def artifact_preview(artifact_id: str, db: Session = Depends(get_db)):
    artifact = db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    html = (
        artifact.content.get("preview_html")
        or (artifact.content.get("files") or {}).get("index.html")
        or artifact.content.get("html")
        or ""
    )
    return Response(content=html, media_type="text/html; charset=utf-8")


@compat_router.post("/artifacts")
async def compat_create_artifact(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return artifact_to_dict(_create_from_payload(db, user, await _payload(request)))


@compat_router.post("/files")
@compat_router.post("/attachments")
async def compat_upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
    purpose: str = "attachment",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return file_asset_to_dict(
        await save_upload(db, user=user, upload=file, conversation_id=conversation_id, purpose=purpose)
    )


@compat_router.get("/files")
@compat_router.get("/attachments")
async def compat_list_files(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_extension_tables(db)
    items = db.scalars(
        select(FileAsset)
        .where(FileAsset.owner_id == user.id, FileAsset.deleted_at.is_(None))
        .order_by(FileAsset.created_at.desc())
    ).all()
    return {"items": [file_asset_to_dict(item) for item in items]}


@compat_router.get("/files/{file_id}/download")
@compat_router.get("/attachments/{file_id}/download")
async def compat_download_file(
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_asset = _owned_file(db, user, file_id)
    return FileResponse(
        attachment_path(file_asset),
        media_type=file_asset.content_type,
        filename=file_asset.original_filename,
    )


@compat_router.get("/knowledge-bases")
async def compat_list_knowledge_bases(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_extension_tables(db)
    items = db.scalars(
        select(KnowledgeBase)
        .options(selectinload(KnowledgeBase.documents))
        .where(KnowledgeBase.owner_id == user.id, KnowledgeBase.deleted_at.is_(None))
    ).all()
    return {"items": [knowledge_base_to_dict(item) for item in items]}


@compat_router.post("/knowledge-bases")
async def compat_create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_extension_tables(db)
    kb = KnowledgeBase(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        visibility=payload.visibility,
        config=payload.config,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return knowledge_base_to_dict(kb)
