from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin, utcnow, uuid_str
from ..types import ContentJSON, SensitiveJSON

if TYPE_CHECKING:
    from .conversations import Conversation


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    trigger_message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"), nullable=True, index=True)
    started_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    mode: Mapped[str] = mapped_column(String(40), default="manual", index=True)
    workflow_snapshot: Mapped[dict] = mapped_column(SensitiveJSON, default=dict)
    node_states: Mapped[list] = mapped_column(ContentJSON, default=list)
    edge_states: Mapped[list] = mapped_column(ContentJSON, default=list)
    events: Mapped[list] = mapped_column(ContentJSON, default=list)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict] = mapped_column("metadata", SensitiveJSON, default=dict)

    conversation: Mapped["Conversation"] = relationship()
