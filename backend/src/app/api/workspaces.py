from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.response import ok
from app.deps import get_current_user
from db import get_db
from db.models import (
    AuditLog,
    Project,
    ProjectFile,
    PromptTemplate,
    ShortcutCommand,
    User,
    Workspace,
    WorkspaceMember,
    utcnow,
)
from app.schemas.requests import (
    AddWorkspaceMemberRequest,
    CreateProjectRequest,
    CreatePromptTemplateRequest,
    CreateShortcutCommandRequest,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    UpsertProjectFileRequest,
)
from app.schemas.common import ApiResponse, ProjectFileOut, ProjectOut, PromptTemplateOut, ShortcutCommandOut, WorkspaceOut
from app.services.audit import write_audit_log
from app.services.serialization import (
    project_file_to_dict,
    project_to_dict,
    prompt_template_to_dict,
    shortcut_command_to_dict,
    workspace_member_to_dict,
    workspace_to_dict,
)


router = APIRouter(tags=["workspaces"])

WORKSPACE_TEMPLATES = [
    {
        "id": "fullstack-delivery",
        "name": "全链路开发模板",
        "type": "vertical",
        "description": "产品、设计、前端、后端、测试、部署的标准多 Agent 链路。",
        "workflow": {
            "nodes": ["product", "design", "frontend", "backend", "reviewer", "deploy"],
            "edges": [["product", "design"], ["design", "frontend"], ["backend", "reviewer"], ["reviewer", "deploy"]],
            "mode": "hybrid",
        },
        "tools": ["file.read", "file.write", "sandbox.run", "file.summarize", "deploy.preview"],
    },
    {
        "id": "data-analysis",
        "name": "数据分析模板",
        "type": "cross",
        "description": "采集、清洗、分析、可视化与报告生成。",
        "workflow": {"nodes": ["collector", "analyst", "visualizer", "reviewer"], "mode": "serial"},
        "tools": ["python", "database", "chart", "report"],
    },
    {
        "id": "custom-lab",
        "name": "自定义实验模板",
        "type": "custom",
        "description": "从空白工作区开始配置 Agent、知识库、MCP 工具和快捷指令。",
        "workflow": {"nodes": [], "mode": "manual"},
        "tools": [],
    },
]


async def ensure_workspace_tables(db: AsyncSession) -> None:
    for table in (
        Workspace.__table__,
        WorkspaceMember.__table__,
        Project.__table__,
        ProjectFile.__table__,
        PromptTemplate.__table__,
        ShortcutCommand.__table__,
        AuditLog.__table__,
    ):
        await db.run_sync(lambda session: table.create(bind=session.get_bind(), checkfirst=True))


def _workspace_query(user: User):
    member_workspace_ids = select(WorkspaceMember.workspace_id).where(
        WorkspaceMember.user_id == user.id,
        WorkspaceMember.left_at.is_(None),
    )
    return (
        select(Workspace)
        .options(selectinload(Workspace.members).selectinload(WorkspaceMember.user), selectinload(Workspace.projects))
        .where(Workspace.deleted_at.is_(None))
        .where((Workspace.owner_id == user.id) | (Workspace.id.in_(member_workspace_ids)))
    )


async def _get_workspace(db: AsyncSession, user: User, workspace_id: str) -> Workspace:
    await ensure_workspace_tables(db)
    workspace = await db.scalar(_workspace_query(user).where(Workspace.id == workspace_id))
    if not workspace:
        raise NotFoundError("工作区不存在")
    return workspace


def _can_manage(workspace: Workspace, user: User) -> bool:
    if user.role == "admin" or workspace.owner_id == user.id:
        return True
    return any(
        member.user_id == user.id and member.left_at is None and member.role in {"owner", "admin"}
        for member in workspace.members
    )


@router.get("/workspace-templates", response_model=ApiResponse[dict])
async def workspace_templates(_user: User = Depends(get_current_user)):
    return ok({"items": WORKSPACE_TEMPLATES})


@router.get("/workspaces", response_model=ApiResponse[dict])
async def list_workspaces(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await ensure_workspace_tables(db)
    items = (await db.scalars(_workspace_query(user).order_by(Workspace.updated_at.desc()))).all()
    return ok({"items": [workspace_to_dict(item) for item in items], "total": len(items)})


@router.post("/workspaces", response_model=ApiResponse[WorkspaceOut])
async def create_workspace(
    payload: CreateWorkspaceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_workspace_tables(db)
    duplicate = await db.scalar(
        select(Workspace).where(
            Workspace.owner_id == user.id, Workspace.name == payload.name, Workspace.deleted_at.is_(None)
        )
    )
    if duplicate:
        raise ValidationAppError("同名工作区已存在")
    template = next((item for item in WORKSPACE_TEMPLATES if item["id"] == payload.config.get("template_id")), None)
    workspace = Workspace(
        owner_id=user.id,
        name=payload.name,
        description=payload.description or (template or {}).get("description", ""),
        type=payload.type or (template or {}).get("type", "custom"),
        tags=payload.tags,
        config={**payload.config, "tools": (template or {}).get("tools", [])},
        workflow=payload.workflow or (template or {}).get("workflow", {}),
        resource_bindings={"knowledge_base_ids": [], "mcp_server_ids": [], "agent_ids": []},
        last_active_at=utcnow(),
    )
    db.add(workspace)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner", permissions=["*"]))
    await write_audit_log(
        db,
        user=user,
        action="workspace.create",
        target_type="workspace",
        target_id=workspace.id,
        detail={"name": workspace.name},
    )
    await db.commit()
    await db.refresh(workspace)
    return ok(workspace_to_dict(await _get_workspace(db, user, workspace.id)), "工作区已创建")


@router.get("/workspaces/{workspace_id}", response_model=ApiResponse[WorkspaceOut])
async def get_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return ok(workspace_to_dict(await _get_workspace(db, user, workspace_id)))


@router.patch("/workspaces/{workspace_id}", response_model=ApiResponse[WorkspaceOut])
async def update_workspace(
    workspace_id: str,
    payload: UpdateWorkspaceRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    if not _can_manage(workspace, user):
        raise ForbiddenError("只有工作区所有者或管理员可以修改配置")
    data = payload.model_dump(exclude_unset=True)
    for field in ["name", "description", "status", "tags", "config", "workflow", "resource_bindings"]:
        if field in data and data[field] is not None:
            setattr(workspace, field, data[field])
    workspace.last_active_at = utcnow()
    await write_audit_log(db, user=user, action="workspace.update", target_type="workspace", target_id=workspace.id)
    await db.commit()
    return ok(workspace_to_dict(await _get_workspace(db, user, workspace.id)), "工作区已更新")


@router.post("/workspaces/{workspace_id}/archive", response_model=ApiResponse[WorkspaceOut])
async def archive_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    if not _can_manage(workspace, user):
        raise ForbiddenError("无权归档工作区")
    workspace.status = "archived"
    await db.commit()
    return ok(workspace_to_dict(workspace), "工作区已归档")


@router.post("/workspaces/{workspace_id}/clone", response_model=ApiResponse[WorkspaceOut])
async def clone_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = await _get_workspace(db, user, workspace_id)
    clone = Workspace(
        owner_id=user.id,
        name=f"{source.name} 副本",
        description=source.description,
        type=source.type,
        tags=source.tags,
        config=source.config,
        workflow=source.workflow,
        resource_bindings=source.resource_bindings,
        last_active_at=utcnow(),
    )
    db.add(clone)
    await db.flush()
    db.add(WorkspaceMember(workspace_id=clone.id, user_id=user.id, role="owner", permissions=["*"]))
    await db.commit()
    return ok(workspace_to_dict(await _get_workspace(db, user, clone.id)), "工作区已克隆")


@router.delete("/workspaces/{workspace_id}", response_model=ApiResponse[dict])
async def delete_workspace(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    if workspace.owner_id != user.id and user.role != "admin":
        raise ForbiddenError("只有工作区所有者可以删除")
    workspace.deleted_at = utcnow()
    workspace.status = "deleted"
    await db.commit()
    return ok({"id": workspace.id, "deleted": True})


@router.get("/workspaces/{workspace_id}/members", response_model=ApiResponse[dict])
async def list_workspace_members(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    return ok({"items": [workspace_member_to_dict(item) for item in workspace.members if item.left_at is None]})


@router.post("/workspaces/{workspace_id}/members", response_model=ApiResponse[WorkspaceOut])
async def add_workspace_member(
    workspace_id: str,
    payload: AddWorkspaceMemberRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    if not _can_manage(workspace, user):
        raise ForbiddenError("无权添加工作区成员")
    member_user = await db.get(User, payload.user_id)
    if not member_user:
        raise NotFoundError("用户不存在")
    existing = next((item for item in workspace.members if item.user_id == payload.user_id), None)
    if existing:
        existing.left_at = None
        existing.role = payload.role
        existing.permissions = payload.permissions
    else:
        db.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=payload.user_id,
                role=payload.role,
                permissions=payload.permissions,
            )
        )
    await db.commit()
    return ok(workspace_to_dict(await _get_workspace(db, user, workspace.id)), "成员已加入")


@router.post("/workspaces/{workspace_id}/projects", response_model=ApiResponse[ProjectOut])
async def create_project(
    workspace_id: str,
    payload: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    project = Project(
        workspace_id=workspace.id,
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        type=payload.type,
        tags=payload.tags,
        context=payload.context,
    )
    db.add(project)
    workspace.last_active_at = utcnow()
    await db.commit()
    await db.refresh(project)
    return ok(project_to_dict(project), "项目已创建")


@router.get("/workspaces/{workspace_id}/projects", response_model=ApiResponse[dict])
async def list_projects(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    projects = (await db.scalars(
        select(Project).where(Project.workspace_id == workspace.id, Project.deleted_at.is_(None)).order_by(Project.updated_at.desc())
    )).all()
    return ok({"items": [project_to_dict(item) for item in projects], "total": len(projects)})


@router.put("/projects/{project_id}/files", response_model=ApiResponse[ProjectFileOut])
async def upsert_project_file(
    project_id: str,
    payload: UpsertProjectFileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await db.scalar(
        select(Project)
        .join(Workspace, Workspace.id == Project.workspace_id)
        .where(Project.id == project_id, Project.deleted_at.is_(None), Workspace.owner_id == user.id)
    )
    if not project:
        raise NotFoundError("项目不存在")
    checksum = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
    file = await db.scalar(select(ProjectFile).where(ProjectFile.project_id == project.id, ProjectFile.path == payload.path))
    if file:
        file.content = payload.content
        file.language = payload.language
        file.checksum = checksum
        file.size = len(payload.content.encode("utf-8"))
        file.version += 1
    else:
        file = ProjectFile(
            project_id=project.id,
            path=payload.path,
            language=payload.language,
            content=payload.content,
            checksum=checksum,
            size=len(payload.content.encode("utf-8")),
        )
        db.add(file)
        project.file_count += 1
    project.current_version += 1
    await db.commit()
    await db.refresh(file)
    return ok(project_file_to_dict(file), "项目文件已保存")


@router.get("/projects/{project_id}/files", response_model=ApiResponse[dict])
async def list_project_files(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await db.scalar(
        select(Project)
        .join(Workspace, Workspace.id == Project.workspace_id)
        .where(Project.id == project_id, Project.deleted_at.is_(None), Workspace.owner_id == user.id)
    )
    if not project:
        raise NotFoundError("项目不存在")
    files = (await db.scalars(select(ProjectFile).where(ProjectFile.project_id == project.id).order_by(ProjectFile.path))).all()
    return ok({"items": [project_file_to_dict(item, include_content=False) for item in files], "total": len(files)})


@router.post("/workspaces/{workspace_id}/prompt-templates", response_model=ApiResponse[PromptTemplateOut])
async def create_prompt_template(
    workspace_id: str,
    payload: CreatePromptTemplateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    template = PromptTemplate(
        owner_id=user.id,
        workspace_id=workspace.id,
        name=payload.name,
        description=payload.description,
        scope=payload.scope,
        category=payload.category,
        content=payload.content,
        variables=payload.variables,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return ok(prompt_template_to_dict(template), "提示词模板已创建")


@router.post("/workspaces/{workspace_id}/shortcut-commands", response_model=ApiResponse[ShortcutCommandOut])
async def create_shortcut_command(
    workspace_id: str,
    payload: CreateShortcutCommandRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    workspace = await _get_workspace(db, user, workspace_id)
    command = ShortcutCommand(
        workspace_id=workspace.id,
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        prompt_template=payload.prompt_template,
        agent_route=payload.agent_route,
        parameters_schema=payload.parameters_schema,
    )
    db.add(command)
    await db.commit()
    await db.refresh(command)
    return ok(shortcut_command_to_dict(command), "快捷指令已创建")
