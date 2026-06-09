from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, uuid_str
from ..types import ContentJSON, EncryptedText, SensitiveJSON

if TYPE_CHECKING:
    pass


class FileAsset(Base, TimestampMixin):
    __tablename__ = "file_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), nullable=True, index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    artifact_id: Mapped[str | None] = mapped_column(ForeignKey("artifacts.id"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(160), default="application/octet-stream")
    size: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(128), index=True)
    storage_path: Mapped[str] = mapped_column(Text)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(String(40), default="attachment", index=True)
    parse_status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    extracted_text: Mapped[str] = mapped_column(EncryptedText, default="")
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(EncryptedText, default="")
    scope: Mapped[str] = mapped_column(String(30), default="personal", index=True)
    visibility: Mapped[str] = mapped_column(String(30), default="private", index=True)
    chunk_strategy: Mapped[str] = mapped_column(String(40), default="recursive")
    embedding_model: Mapped[str] = mapped_column(String(120), default="mock-hash-embedding")
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="ready", index=True)
    config: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)

    documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="knowledge_base", cascade="all, delete-orphan"
    )


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    knowledge_base_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    file_asset_id: Mapped[str | None] = mapped_column(ForeignKey("file_assets.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(40), default="upload", index=True)
    source_uri: Mapped[str] = mapped_column(EncryptedText, default="")
    content: Mapped[str] = mapped_column(EncryptedText, default="")
    chunks: Mapped[list] = mapped_column(ContentJSON, default=list)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    index_status: Mapped[str] = mapped_column(String(40), default="indexed", index=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)

    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")
    file_asset: Mapped["FileAsset | None"] = relationship()
