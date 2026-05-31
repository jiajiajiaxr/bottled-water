from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import ForbiddenError, NotFoundError
from app.core.response import ok
from app.deps import get_current_user
from app.models import KnowledgeBase, KnowledgeDocument, User, utcnow
from app.schemas.common import ApiResponse, KnowledgeBaseOut, KnowledgeDocumentOut
from app.schemas.requests import CreateKnowledgeBaseRequest, ImportKnowledgeTextRequest, RetrieveKnowledgeRequest
from app.services.files import save_upload
from app.services.knowledge import build_context_snippet, index_document, retrieve
from app.services.serialization import (
    file_asset_to_dict,
    knowledge_base_to_dict,
    knowledge_document_to_dict,
)


router = APIRouter(tags=["knowledge"])


async def _get_kb(db: AsyncSession, user: User, kb_id: str) -> KnowledgeBase:
    kb = await db.scalar(select(KnowledgeBase).where(KnowledgeBase.id == kb_id, KnowledgeBase.deleted_at.is_(None)))
    if not kb:
        raise NotFoundError("知识库不存在")
    if kb.owner_id != user.id and kb.visibility != "public" and user.role != "admin":
        raise ForbiddenError("无权访问该知识库")
    return kb


@router.get("/knowledge-bases", response_model=ApiResponse[dict])
async def list_knowledge_bases(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = (await db.scalars(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.deleted_at.is_(None),
            (KnowledgeBase.owner_id == user.id) | (KnowledgeBase.visibility == "public"),
        )
        .order_by(KnowledgeBase.updated_at.desc())
    )).all()
    return ok({"items": [knowledge_base_to_dict(item) for item in items], "total": len(items)})


@router.post("/knowledge-bases", response_model=ApiResponse[KnowledgeBaseOut])
async def create_knowledge_base(
    payload: CreateKnowledgeBaseRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
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


@router.get("/knowledge-bases/{kb_id}", response_model=ApiResponse[KnowledgeBaseOut])
async def get_knowledge_base(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(knowledge_base_to_dict(await _get_kb(db, user, kb_id)))


@router.delete("/knowledge-bases/{kb_id}", response_model=ApiResponse[dict])
async def delete_knowledge_base(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _get_kb(db, user, kb_id)
    if kb.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只有知识库所有者可删除")
    kb.deleted_at = utcnow()
    kb.status = "deleted"
    await db.commit()
    return ok({"id": kb.id, "deleted": True})


@router.get("/knowledge-bases/{kb_id}/documents", response_model=ApiResponse[dict])
async def list_documents(
    kb_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _get_kb(db, user, kb_id)
    docs = (await db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.knowledge_base_id == kb.id, KnowledgeDocument.deleted_at.is_(None))
        .order_by(KnowledgeDocument.created_at.desc())
    )).all()
    return ok({"items": [knowledge_document_to_dict(item) for item in docs], "total": len(docs)})


@router.post("/knowledge-bases/{kb_id}/documents", response_model=ApiResponse[KnowledgeDocumentOut])
async def import_text_document(
    kb_id: str,
    payload: ImportKnowledgeTextRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _get_kb(db, user, kb_id)
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
    return ok(knowledge_document_to_dict(document), "文档已索引")


@router.post("/knowledge-bases/{kb_id}/documents/upload", response_model=ApiResponse[dict])
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _get_kb(db, user, kb_id)
    asset = await save_upload(db, user=user, upload=file, purpose="knowledge")
    await db.refresh(asset)
    document = await index_document(
        db,
        kb,
        title=asset.original_filename,
        content=asset.extracted_text or f"文件 {asset.original_filename} 已上传，暂不支持二进制内容解析。",
        source_type="upload",
        source_uri=asset.storage_path,
        file_asset_id=asset.id,
    )
    await db.commit()
    return ok(
        {"file": file_asset_to_dict(asset), "document": knowledge_document_to_dict(document)},
        "知识文档上传并索引完成",
    )


@router.post("/knowledge-bases/{kb_id}/retrieve", response_model=ApiResponse[dict])
async def retrieve_knowledge(
    kb_id: str,
    payload: RetrieveKnowledgeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    kb = await _get_kb(db, user, kb_id)
    results = await retrieve(
        db,
        kb,
        query=payload.query,
        top_k=payload.top_k,
        threshold=payload.similarity_threshold,
    )
    return ok({"items": results, "context": build_context_snippet(results), "mode": payload.mode})
