from __future__ import annotations

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError
from app.models import Skill, SkillRun, User, Workspace


def ensure_skill_tables(db: Session) -> None:
    for table in (Skill.__table__, SkillRun.__table__):
        table.create(bind=db.get_bind(), checkfirst=True)


def visible_skill_filter(user: User):
    if user.role == "admin":
        return true()
    return (Skill.owner_id == user.id) | (Skill.owner_id.is_(None))


def visible_skill_query(db: Session, user: User, workspace_id: str | None = None):
    ensure_skill_tables(db)
    query = select(Skill).where(Skill.deleted_at.is_(None)).where(visible_skill_filter(user))
    if workspace_id:
        query = query.where(or_(Skill.workspace_id == workspace_id, Skill.workspace_id.is_(None)))
    return query


def validate_workspace(db: Session, user: User, workspace_id: str | None) -> None:
    if not workspace_id:
        return
    workspace = db.get(Workspace, workspace_id)
    if not workspace or workspace.deleted_at is not None:
        raise NotFoundError("Workspace not found")
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("No permission for this workspace")


def get_skill_for_user(db: Session, user: User, skill_id: str) -> Skill:
    ensure_skill_tables(db)
    skill = db.scalar(select(Skill).where(Skill.id == skill_id, Skill.deleted_at.is_(None)))
    if not skill:
        raise NotFoundError("Skill not found")
    if skill.owner_id not in {None, user.id} and user.role != "admin":
        raise ForbiddenError("No permission for this skill")
    return skill


def ensure_skill_owner(skill: Skill, user: User) -> None:
    if skill.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("Only the owner can modify this skill")
