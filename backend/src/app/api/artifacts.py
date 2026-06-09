from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from pathlib import Path

from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import Artifact, Conversation, FileAsset, KnowledgeBase, User, utcnow
from app.schemas.common import (
    ApiResponse,
    ArtifactOut,
    FileAssetOut,
    KnowledgeBaseOut,
    KnowledgeDocumentOut,
)
from app.schemas.requests import (
    CreateArtifactRequest,
    CreateKnowledgeBaseRequest,
    ImportKnowledgeTextRequest,
    RetrieveKnowledgeRequest,
    SaveArtifactRequest,
)
from app.services.artifacts import (
    build_demo_html,
    compute_artifact_diff,
    create_artifact,
    update_artifact_files,
)
from app.services.files.previewers.office import build_office_preview, is_office_file
from app.services.files import (
    attachment_path,
    encrypted_file_response_content,
    ensure_extension_tables,
    save_upload,
)
from app.services.knowledge import index_document, retrieve
from app.services.serialization import (
    artifact_to_dict,
    file_asset_to_dict,
    knowledge_base_to_dict,
    knowledge_document_to_dict,
)
from app.services.tools.builtins.artifact.export import default_export_format, export_artifact


router = APIRouter(tags=["artifacts"])
compat_router = APIRouter(tags=["artifacts-compat"])


async def _owned_artifact(db: AsyncSession, user: User, artifact_id: str) -> Artifact:
    if not hasattr(db, "run_sync"):
        artifact = db.get(Artifact, artifact_id)
        if not artifact:
            raise NotFoundError("产物不存在")
        conversation = db.get(Conversation, artifact.conversation_id)
        if not conversation or conversation.creator_id != user.id:
            raise NotFoundError("产物不存在")
        return artifact
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    conversation = await db.get(Conversation, artifact.conversation_id)
    if not conversation or conversation.creator_id != user.id:
        raise NotFoundError("产物不存在")
    return artifact


async def _owned_file(db: AsyncSession, user: User, file_id: str) -> FileAsset:
    await ensure_extension_tables(db)
    file_asset = await db.get(FileAsset, file_id)
    if not file_asset or file_asset.owner_id != user.id or file_asset.deleted_at is not None:
        raise NotFoundError("文件不存在")
    return file_asset


async def _owned_kb(db: AsyncSession, user: User, knowledge_base_id: str) -> KnowledgeBase:
    await ensure_extension_tables(db)
    kb = await db.scalar(
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


async def _latest_for_conversation(db: AsyncSession, user: User, conversation_id: str) -> Artifact:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.creator_id == user.id,
            Conversation.deleted_at.is_(None),
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    artifact = await db.scalar(
        select(Artifact)
        .where(Artifact.conversation_id == conversation.id, Artifact.deleted_at.is_(None))
        .order_by(Artifact.updated_at.desc())
    )
    if not artifact:
        raise NotFoundError("当前会话暂无产物")
    return artifact


async def _create_from_payload(
    db: AsyncSession, user: User, payload: CreateArtifactRequest
) -> Artifact:
    conversation_id = payload.conversation_id
    if not conversation_id:
        raise ValidationAppError("conversation_id 不能为空")
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.creator_id == user.id
        )
    )
    if not conversation:
        raise NotFoundError("会话不存在")
    content = payload.content or {}
    html = content.get("html") or (content.get("files") or {}).get("index.html")
    if not html:
        html = build_demo_html(payload.title or "Acceptance Preview")
    artifact = await create_artifact(
        db,
        conversation,
        task=None,
        name=payload.title or payload.name or "预览产物",
        html=html,
    )
    await db.commit()
    await db.refresh(artifact)
    return artifact


@router.get(
    "/conversations/{conversation_id}/artifacts", response_model=ApiResponse[list[ArtifactOut]]
)
async def list_conversation_artifacts(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        artifact = await _latest_for_conversation(db, user, conversation_id)
    except NotFoundError:
        return ok([])
    return ok([artifact_to_dict(artifact)])


@router.get("/conversations/{conversation_id}/artifact", response_model=ApiResponse[ArtifactOut])
async def get_conversation_artifact(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(artifact_to_dict(await _latest_for_conversation(db, user, conversation_id)))


@router.post("/artifacts", response_model=ApiResponse[ArtifactOut])
async def create_artifact_endpoint(
    payload: CreateArtifactRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(artifact_to_dict(await _create_from_payload(db, user, payload)), "产物已创建")


@router.get("/artifacts/{artifact_id}", response_model=ApiResponse[ArtifactOut])
async def get_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(artifact_to_dict(await _owned_artifact(db, user, artifact_id)))


@router.get("/artifacts/{artifact_id}/content", response_model=ApiResponse[dict])
async def get_artifact_content(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await _owned_artifact(db, user, artifact_id)
    return ok(artifact.content)


@router.get("/artifacts/{artifact_id}/exports", response_model=ApiResponse[dict])
async def list_artifact_exports(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await _owned_artifact(db, user, artifact_id)
    formats = ["html", "markdown", "json", "zip"]
    if artifact.type == "document":
        formats.insert(0, "pdf")
        formats.insert(0, "docx")
    elif artifact.type == "spreadsheet":
        formats.insert(0, "xlsx")
    elif artifact.type == "slides":
        formats.insert(0, "pptx")
    elif artifact.type in {"web_app", "code"}:
        formats.insert(0, "zip")
    formats = list(dict.fromkeys(formats))
    return ok(
        {
            "artifact_id": artifact.id,
            "default_format": default_export_format(artifact),
            "formats": [
                {"format": item, "url": f"/api/v1/artifacts/{artifact.id}/export?format={item}"}
                for item in formats
            ],
        }
    )


@router.get("/artifacts/{artifact_id}/export")
async def download_artifact_export(
    artifact_id: str,
    format: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):

    artifact = await _owned_artifact(db, user, artifact_id)
    try:
        exported = export_artifact(artifact, format)
    except ValueError as exc:
        raise ValidationAppError(str(exc)) from exc
    return Response(
        content=exported.content,
        media_type=exported.media_type,
        headers={"Content-Disposition": _attachment_header(exported.filename)},
    )


@router.get("/artifacts/{artifact_id}/preview-pdf")
async def download_artifact_preview_pdf(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await _owned_artifact(db, user, artifact_id)
    exported = export_artifact(artifact, default_export_format(artifact))
    filename = exported.filename
    media_type = exported.media_type
    if media_type == "application/pdf" or Path(filename).suffix.lower() == ".pdf":
        return Response(
            content=exported.content,
            media_type="application/pdf",
            headers={"Content-Disposition": _inline_header(filename)},
        )
    if not is_office_file(media_type, filename):
        raise ValidationAppError("当前产物不是可转换的 Office 文件")
    result = build_office_preview(
        workspace_id=_artifact_workspace_id(artifact),
        node_id=f"artifact:{artifact.id}",
        target={"kind": "artifact", "artifact": artifact, "bytes": exported.content},
        filename=filename,
        mime_type=media_type,
    )
    if not result.preview_pdf_path:
        raise ValidationAppError(result.error or "Office PDF 预览生成失败")
    return FileResponse(
        str(result.preview_pdf_path),
        media_type="application/pdf",
        filename=f"{Path(filename).stem or artifact.name}.preview.pdf",
    )


@router.put("/artifacts/{artifact_id}", response_model=ApiResponse[ArtifactOut])
@router.post("/artifacts/{artifact_id}/versions", response_model=ApiResponse[ArtifactOut])
async def save_artifact(
    artifact_id: str,
    payload: SaveArtifactRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _owned_artifact(db, user, artifact_id)
    files = payload.files
    if not files and payload.code:
        files = {"index.html": payload.code}
    if not files and payload.content and payload.content.get("files"):
        files = payload.content["files"]
    if not files:
        raise ValidationAppError("产物文件不能为空")
    artifact = await update_artifact_files(
        db, artifact_id, files, payload.change_summary or "在线编辑保存"
    )
    return ok(artifact_to_dict(artifact), "产物已保存")


@router.post("/artifacts/{artifact_id}/diff", response_model=ApiResponse[dict])
async def artifact_diff(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    artifact = await _owned_artifact(db, user, artifact_id)
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


@router.post("/files", response_model=ApiResponse[FileAssetOut])
@router.post("/attachments", response_model=ApiResponse[FileAssetOut])
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
    purpose: str = "attachment",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if conversation_id:
        conversation = await db.scalar(
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


@router.get("/files", response_model=ApiResponse[dict])
@router.get("/attachments", response_model=ApiResponse[dict])
async def list_files(
    conversation_id: str | None = None,
    purpose: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_extension_tables(db)
    query = select(FileAsset).where(FileAsset.owner_id == user.id, FileAsset.deleted_at.is_(None))
    if conversation_id:
        query = query.where(FileAsset.conversation_id == conversation_id)
    if purpose:
        query = query.where(FileAsset.purpose == purpose)
    items = (await db.scalars(query.order_by(FileAsset.created_at.desc()))).all()
    return ok({"items": [file_asset_to_dict(item) for item in items], "total": len(items)})


@router.get("/files/{file_id}", response_model=ApiResponse[FileAssetOut])
@router.get("/attachments/{file_id}", response_model=ApiResponse[FileAssetOut])
async def get_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(file_asset_to_dict(await _owned_file(db, user, file_id)))


@router.get("/files/{file_id}/download")
@router.get("/attachments/{file_id}/download")
async def download_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_asset = await _owned_file(db, user, file_id)
    decrypted = encrypted_file_response_content(file_asset)
    if decrypted is not None:
        return Response(
            content=decrypted,
            media_type=file_asset.content_type,
            headers={"Content-Disposition": _attachment_header(file_asset.original_filename)},
        )
    return FileResponse(
        attachment_path(file_asset),
        media_type=file_asset.content_type,
        filename=file_asset.original_filename,
    )


@router.delete("/files/{file_id}", response_model=ApiResponse[dict])
@router.delete("/attachments/{file_id}", response_model=ApiResponse[dict])
async def delete_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_asset = await _owned_file(db, user, file_id)
    file_asset.deleted_at = utcnow()
    file_asset.parse_status = "deleted"
    await db.commit()
    return ok({"id": file_asset.id, "deleted": True})


@router.get("/knowledge-bases", response_model=ApiResponse[dict])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_extension_tables(db)
    items = (
        await db.scalars(
            select(KnowledgeBase)
            .options(selectinload(KnowledgeBase.documents))
            .where(KnowledgeBase.owner_id == user.id, KnowledgeBase.deleted_at.is_(None))
            .order_by(KnowledgeBase.updated_at.desc())
        )
    ).all()
    return ok({"items": [knowledge_base_to_dict(item) for item in items], "total": len(items)})


@router.post("/knowledge-bases", response_model=ApiResponse[KnowledgeBaseOut])
async def create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_extension_tables(db)
    kb = KnowledgeBase(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        visibility=payload.visibility,
        config=payload.config,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return ok(knowledge_base_to_dict(kb), "知识库已创建")


@router.get("/knowledge-bases/{knowledge_base_id}", response_model=ApiResponse[KnowledgeBaseOut])
async def get_knowledge_base(
    knowledge_base_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(knowledge_base_to_dict(await _owned_kb(db, user, knowledge_base_id)))


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=ApiResponse[KnowledgeDocumentOut],
)
async def import_knowledge_text(
    knowledge_base_id: str,
    payload: ImportKnowledgeTextRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _owned_kb(db, user, knowledge_base_id)
    document = await index_document(
        db,
        kb,
        title=payload.title,
        content=payload.content,
        source_type=payload.source_type,
        source_uri=payload.source_uri,
    )
    await db.commit()
    await db.refresh(document)
    await db.refresh(kb)
    return ok(knowledge_document_to_dict(document), "文档已索引")


@router.post(
    "/knowledge-bases/{knowledge_base_id}/documents/upload", response_model=ApiResponse[dict]
)
async def upload_knowledge_document(
    knowledge_base_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _owned_kb(db, user, knowledge_base_id)
    file_asset = await save_upload(db, user=user, upload=file, purpose="knowledge")
    content = (
        file_asset.extracted_text or f"{file_asset.original_filename} ({file_asset.content_type})"
    )
    document = await index_document(
        db,
        kb,
        title=file_asset.original_filename,
        content=content,
        source_type="upload",
        source_uri=file_asset.public_url or f"/api/v1/files/{file_asset.id}/download",
        file_asset_id=file_asset.id,
    )
    await db.commit()
    await db.refresh(document)
    return ok(
        {"file": file_asset_to_dict(file_asset), "document": knowledge_document_to_dict(document)},
        "文档已上传并索引",
    )


@router.get("/knowledge-bases/{knowledge_base_id}/documents", response_model=ApiResponse[dict])
async def list_knowledge_documents(
    knowledge_base_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _owned_kb(db, user, knowledge_base_id)
    documents = [item for item in kb.documents if item.deleted_at is None]
    return ok(
        {"items": [knowledge_document_to_dict(item) for item in documents], "total": len(documents)}
    )


@router.post("/knowledge-bases/{knowledge_base_id}/retrieve", response_model=ApiResponse[dict])
async def retrieve_knowledge(
    knowledge_base_id: str,
    payload: RetrieveKnowledgeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _owned_kb(db, user, knowledge_base_id)
    results = await retrieve(
        db,
        kb,
        query=payload.query,
        top_k=payload.top_k,
        threshold=payload.similarity_threshold,
    )
    return ok({"items": results, "total": len(results), "mode": payload.mode})


@router.get("/artifacts/{artifact_id}/preview")
async def artifact_preview(artifact_id: str, db: AsyncSession = Depends(get_db)):
    artifact = await db.get(Artifact, artifact_id)
    if not artifact:
        raise NotFoundError("产物不存在")
    html = (
        artifact.content.get("preview_html")
        or (artifact.content.get("files") or {}).get("index.html")
        or artifact.content.get("html")
        or ""
    )
    from fastapi import Response

    return Response(content=html, media_type="text/html; charset=utf-8")


def _attachment_header(filename: str) -> str:
    from urllib.parse import quote

    return f"attachment; filename*=UTF-8''{quote(filename)}"


def _inline_header(filename: str) -> str:
    from urllib.parse import quote

    return f"inline; filename*=UTF-8''{quote(filename)}"


def _artifact_workspace_id(artifact: Artifact) -> str:
    content = artifact.content or {}
    source = content.get("source_file") if isinstance(content.get("source_file"), dict) else {}
    path_value = str(source.get("storage_path") or "")
    marker = f"{Path('workspaces')}"
    if marker in path_value:
        parts = Path(path_value).parts
        if "workspaces" in parts:
            index = parts.index("workspaces")
            if len(parts) > index + 1:
                return parts[index + 1]
    return "default"


# ----- compat routes -----


@compat_router.post("/artifacts", response_model=ArtifactOut)
async def compat_create_artifact(
    payload: CreateArtifactRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return artifact_to_dict(await _create_from_payload(db, user, payload))


@compat_router.post("/files", response_model=ApiResponse[FileAssetOut])
@compat_router.post("/attachments", response_model=ApiResponse[FileAssetOut])
async def compat_upload_file(
    file: UploadFile = File(...),
    conversation_id: str | None = None,
    purpose: str = "attachment",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(
        file_asset_to_dict(
            await save_upload(
                db, user=user, upload=file, conversation_id=conversation_id, purpose=purpose
            )
        )
    )


@compat_router.get("/files", response_model=ApiResponse[dict])
@compat_router.get("/attachments", response_model=ApiResponse[dict])
async def compat_list_files(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_extension_tables(db)
    items = (
        await db.scalars(
            select(FileAsset)
            .where(FileAsset.owner_id == user.id, FileAsset.deleted_at.is_(None))
            .order_by(FileAsset.created_at.desc())
        )
    ).all()
    return ok({"items": [file_asset_to_dict(item) for item in items]})


@compat_router.get("/files/{file_id}/download")
@compat_router.get("/attachments/{file_id}/download")
async def compat_download_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    file_asset = await _owned_file(db, user, file_id)
    decrypted = encrypted_file_response_content(file_asset)
    if decrypted is not None:
        return Response(
            content=decrypted,
            media_type=file_asset.content_type,
            headers={"Content-Disposition": _attachment_header(file_asset.original_filename)},
        )
    return FileResponse(
        attachment_path(file_asset),
        media_type=file_asset.content_type,
        filename=file_asset.original_filename,
    )


@compat_router.get("/knowledge-bases", response_model=ApiResponse[list[KnowledgeBaseOut]])
async def compat_list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_extension_tables(db)
    items = (
        await db.scalars(
            select(KnowledgeBase)
            .options(selectinload(KnowledgeBase.documents))
            .where(KnowledgeBase.owner_id == user.id, KnowledgeBase.deleted_at.is_(None))
        )
    ).all()
    return ok([knowledge_base_to_dict(item) for item in items])


@compat_router.post("/knowledge-bases", response_model=ApiResponse[KnowledgeBaseOut])
async def compat_create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_extension_tables(db)
    kb = KnowledgeBase(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        visibility=payload.visibility,
        config=payload.config,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return ok(knowledge_base_to_dict(kb))
