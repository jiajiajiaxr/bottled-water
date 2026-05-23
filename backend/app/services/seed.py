from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Agent,
    Conversation,
    ConversationParticipant,
    Message,
    Permission,
    Role,
    RolePermission,
    McpServer,
    ModelConfig,
    ModelProvider,
    SandboxSession,
    Skill,
    User,
    UserRole,
    UserSettings,
    Workspace,
    WorkspaceMember,
    utcnow,
)
from app.services.tool_registry import get_official_toolbox, ensure_tool_tables


DEFAULT_AGENTS = [
    {
        "name": "Master Agent",
        "type": "master",
        "provider": "ark",
        "avatar_color": "#1677ff",
        "description": "负责需求研判、任务拆解、调度与成果聚合。",
        "system_prompt": "你是 AgentHub Master Agent，负责需求拆解、权限判断、调度 Worker、聚合 Reviewer 结论和最终交付；内部调度信息不要直接暴露给用户。",
        "tools": get_official_toolbox("master"),
        "capabilities": [
            {"label": "调度", "category": "编排", "proficiency": 5},
            {"label": "拆解", "category": "编排", "proficiency": 5},
            {"label": "聚合", "category": "编排", "proficiency": 4},
            {"label": "审查", "category": "质量", "proficiency": 4},
        ],
    },
    {
        "name": "Frontend Worker",
        "type": "frontend",
        "provider": "ark",
        "avatar_color": "#059669",
        "description": "React、TypeScript、Ant Design 与交互实现专家。",
        "system_prompt": "你是 Frontend Worker，使用授权工具完成前端实现、Web 产物生成、浏览器预览和交互验收，输出可验证的修改摘要。",
        "tools": get_official_toolbox("frontend"),
        "capabilities": [
            {"label": "前端", "category": "编码", "proficiency": 5},
            {"label": "React", "category": "编码", "proficiency": 5},
            {"label": "UI", "category": "设计", "proficiency": 4},
        ],
    },
    {
        "name": "Backend Worker",
        "type": "backend",
        "provider": "ark",
        "avatar_color": "#7C3AED",
        "description": "FastAPI、SQLAlchemy、PostgreSQL 与实时服务专家。",
        "system_prompt": "你是 Backend Worker，负责 API、数据库、任务队列、实时事件和测试验证，优先使用授权工具检查并返回可落地结果。",
        "tools": get_official_toolbox("backend"),
        "capabilities": [
            {"label": "后端", "category": "编码", "proficiency": 5},
            {"label": "API", "category": "架构", "proficiency": 5},
            {"label": "数据库", "category": "架构", "proficiency": 4},
        ],
    },
    {
        "name": "Reviewer",
        "type": "reviewer",
        "provider": "ark",
        "avatar_color": "#f59e0b",
        "description": "审查产物完整性、一致性、风险和演示可用性。",
        "system_prompt": "你是 Reviewer，负责产物 Diff、测试运行、安全审计和文档审查，只输出审查结论、风险和修复建议。",
        "tools": get_official_toolbox("reviewer"),
        "capabilities": [
            {"label": "审查", "category": "质量", "proficiency": 5},
            {"label": "质量", "category": "质量", "proficiency": 5},
            {"label": "测试", "category": "测试", "proficiency": 4},
        ],
    },
    {
        "name": "Deploy Agent",
        "type": "deploy",
        "provider": "ark",
        "avatar_color": "#dc2626",
        "description": "负责预览链接、静态发布、容器部署和打包。",
        "system_prompt": "你是 Deploy Agent，负责产物导出、预览部署、回滚和发布记录，执行前说明风险并输出部署状态。",
        "tools": get_official_toolbox("deploy"),
        "capabilities": [
            {"label": "部署", "category": "运维", "proficiency": 5},
            {"label": "预览", "category": "运维", "proficiency": 4},
            {"label": "运维", "category": "运维", "proficiency": 4},
        ],
    },
    {
        "name": "Writing Agent",
        "type": "writing",
        "provider": "ark",
        "avatar_color": "#2563eb",
        "description": "负责方案、报告、标书、答辩稿、PDF/Word/PPT 产物写作与修订。",
        "system_prompt": "你是 Writing Agent，面向正式交付写作，能够读取附件、生成结构化正文，并调用 artifact 工具生成 PDF、Word 或 PPT 产物。",
        "tools": get_official_toolbox("writing"),
        "capabilities": [
            {"label": "写作", "category": "文档", "proficiency": 5},
            {"label": "PDF", "category": "产物", "proficiency": 4},
            {"label": "PPT", "category": "产物", "proficiency": 4},
            {"label": "审稿", "category": "质量", "proficiency": 4},
        ],
    },
    {
        "name": "Daily Chat Agent",
        "type": "chat",
        "provider": "ark",
        "avatar_color": "#14b8a6",
        "description": "负责日常问答、轻量咨询、附件摘要和上下文续聊。",
        "system_prompt": "你是 Daily Chat Agent，负责自然、简洁、可靠的日常对话；遇到文件时先摘要再回答，避免暴露内部推理。",
        "tools": get_official_toolbox("chat"),
        "capabilities": [
            {"label": "聊天", "category": "通用", "proficiency": 5},
            {"label": "问答", "category": "通用", "proficiency": 5},
            {"label": "附件摘要", "category": "文件", "proficiency": 4},
        ],
    },
]

DEFAULT_SKILLS = [
    {
        "name": "需求分析 Skill",
        "description": "把模糊输入压缩成目标、约束、风险和下一步动作，供主控 Agent 快速决策。",
        "category": "analysis",
        "source": "system",
        "content": "分析用户目标，提取关键约束、可执行动作、风险和需要追问的信息。输出简洁结构化结论。",
        "prompt": "你是 AgentHub 内置需求分析 Skill。只返回可用于执行决策的简短分析，不暴露内部推理。",
        "tags": ["analysis", "planning", "agentic-loop"],
        "tools": [],
    },
    {
        "name": "产物审查 Skill",
        "description": "检查生成内容是否符合用户目标、演示可用性、风险和遗漏。",
        "category": "review",
        "source": "system",
        "content": "审查产物完整性、可演示性和风险，给出通过/需修改结论。",
        "prompt": "你是 AgentHub 内置审查 Skill。用简短语言列出关键审查结论和必要修复建议。",
        "tags": ["review", "qa", "artifact"],
        "tools": [],
    },
]

DEFAULT_PERMISSIONS = [
    "session:create",
    "session:read",
    "session:delete",
    "session:export",
    "agent:use",
    "agent:create",
    "agent:update",
    "agent:delete",
    "agent:publish",
    "agent:debug",
    "workspace:create",
    "workspace:read",
    "project:manage",
    "knowledge:manage",
    "file:upload",
    "file:read",
    "file:write",
    "artifact:create",
    "artifact:read",
    "artifact:update",
    "artifact:export",
    "tool:create",
    "tool:update",
    "tool:invoke",
    "sandbox:run",
    "browser:preview",
    "db:inspect",
    "api:test",
    "test:run",
    "security:audit",
    "document:review",
    "deploy:preview",
    "deploy:rollback",
    "workflow:manage",
    "mcp:invoke",
    "security:view",
    "log:view:own",
    "log:view:all",
    "user:manage",
    "config:manage",
]

DEFAULT_ROLE_MAP = {
    "ROLE_USER": ["session:create", "session:read", "session:delete", "session:export", "agent:use", "workspace:create", "workspace:read", "project:manage", "knowledge:manage", "file:upload", "file:read", "artifact:create", "artifact:read", "artifact:export", "workflow:manage", "mcp:invoke", "tool:invoke", "security:view", "log:view:own"],
    "ROLE_AGENT_PROVIDER": ["agent:create", "agent:update", "agent:delete", "agent:publish", "tool:create", "tool:update"],
    "ROLE_DEVELOPER": ["agent:debug", "file:write", "sandbox:run", "db:inspect", "api:test", "test:run", "log:view:all"],
    "ROLE_ADMIN": ["user:manage", "config:manage", "log:view:all", "agent:publish"],
}


def ensure_seed_data(db: Session) -> User:
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == settings.demo_email))
    if not user:
        user = User(
            email=settings.demo_email,
            username=settings.demo_username,
            password_hash=hash_password(settings.demo_password),
            display_name="演示用户",
            role="member",
            status="active",
        )
        db.add(user)
        db.flush()
        db.add(UserSettings(user_id=user.id, theme="light"))

    ensure_tool_tables(db)

    agents = db.scalars(select(Agent)).all()
    if not agents:
        for spec in DEFAULT_AGENTS:
            db.add(
                Agent(
                    owner_id=user.id,
                    name=spec["name"],
                    type=spec["type"],
                    status="online",
                    description=spec["description"],
                    capabilities=spec["capabilities"],
                    last_heartbeat_at=utcnow(),
                    config={
                        "supports_streaming": True,
                        "supports_tool_use": True,
                        "supports_file_upload": True,
                        "agentic_loop": {"enabled": True, "max_steps": 2, "tool_policy": "short_safe_loop"},
                        "system_prompt": spec["system_prompt"],
                        "tools": spec["tools"],
                    },
                    extra={
                        "display_name": spec["name"],
                        "provider": spec["provider"],
                        "avatar_color": spec["avatar_color"],
                        "response_latency_ms": 900,
                        "success_rate": 0.985,
                    },
                )
            )
        db.flush()
        agents = db.scalars(select(Agent)).all()
    else:
        existing_names = {agent.name for agent in agents}
        for spec in DEFAULT_AGENTS:
            if spec["name"] not in existing_names:
                db.add(
                    Agent(
                        owner_id=user.id,
                        name=spec["name"],
                        type=spec["type"],
                        status="online",
                        description=spec["description"],
                        capabilities=spec["capabilities"],
                        last_heartbeat_at=utcnow(),
                        config={
                            "supports_streaming": True,
                            "supports_tool_use": True,
                            "supports_file_upload": True,
                            "agentic_loop": {"enabled": True, "max_steps": 2, "tool_policy": "short_safe_loop"},
                            "system_prompt": spec["system_prompt"],
                            "tools": spec["tools"],
                        },
                        extra={
                            "display_name": spec["name"],
                            "provider": spec["provider"],
                            "avatar_color": spec["avatar_color"],
                            "response_latency_ms": 900,
                            "success_rate": 0.985,
                        },
                    )
                )
        db.flush()
        agents = db.scalars(select(Agent)).all()
        spec_by_type = {spec["type"]: spec for spec in DEFAULT_AGENTS}
        spec_by_name = {spec["name"]: spec for spec in DEFAULT_AGENTS}
        for agent in agents:
            spec = spec_by_name.get(agent.name) or spec_by_type.get(agent.type)
            if not spec:
                continue
            config = dict(agent.config or {})
            config.update(
                {
                    "supports_streaming": True,
                    "supports_tool_use": True,
                    "supports_file_upload": True,
                    "agentic_loop": {"enabled": True, "max_steps": 2, "tool_policy": "short_safe_loop"},
                    "system_prompt": config.get("system_prompt") or spec["system_prompt"],
                    "tools": spec["tools"],
                }
            )
            agent.description = spec["description"]
            agent.capabilities = spec["capabilities"]
            agent.config = config
            agent.extra = {
                **(agent.extra or {}),
                "display_name": spec["name"],
                "provider": spec["provider"],
                "avatar_color": spec["avatar_color"],
            }

    Skill.__table__.create(bind=db.get_bind(), checkfirst=True)
    existing_skill_names = {item.name for item in db.scalars(select(Skill).where(Skill.source == "system")).all()}
    for spec in DEFAULT_SKILLS:
        if spec["name"] in existing_skill_names:
            continue
        db.add(
            Skill(
                owner_id=None,
                workspace_id=None,
                name=spec["name"],
                description=spec["description"],
                category=spec["category"],
                source=spec["source"],
                status="active",
                version="1.0.0",
                content=spec["content"],
                prompt=spec["prompt"],
                tags=spec["tags"],
                tools=spec["tools"],
                config={"builtin": True, "auto_select": True},
            )
        )

    roles = {item.code: item for item in db.scalars(select(Role)).all()}
    if not roles:
        for code in DEFAULT_ROLE_MAP:
            role = Role(code=code, name=code.replace("ROLE_", "").title(), description=f"{code} 默认角色")
            db.add(role)
            roles[code] = role
        permissions = {}
        for code in DEFAULT_PERMISSIONS:
            resource, action = code.split(":", 1)
            permission = Permission(code=code, resource=resource, action=action, description=code)
            db.add(permission)
            permissions[code] = permission
        db.flush()
        for role_code, permission_codes in DEFAULT_ROLE_MAP.items():
            for permission_code in permission_codes:
                db.add(RolePermission(role_id=roles[role_code].id, permission_id=permissions[permission_code].id))
        db.add(UserRole(user_id=user.id, role_id=roles["ROLE_USER"].id, assigned_by=user.id))

    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id, Workspace.name == "默认全栈工作区"))
    if not workspace:
        workspace = Workspace(
            owner_id=user.id,
            name="默认全栈工作区",
            description="预置全链路开发模板，挂载主控、前端、后端、Reviewer 和部署资源。",
            type="vertical",
            tags=["默认", "全链路开发"],
            config={"template_id": "fullstack-delivery", "tools": ["file.read", "file.write", "file.summarize", "deploy.preview"]},
            workflow={
                "mode": "hybrid",
                "nodes": ["master", "frontend", "backend", "reviewer", "deploy"],
                "edges": [["master", "frontend"], ["master", "backend"], ["frontend", "reviewer"], ["backend", "reviewer"], ["reviewer", "deploy"]],
            },
            resource_bindings={"agent_ids": [agent.id for agent in agents[:5]], "knowledge_base_ids": [], "mcp_server_ids": []},
            last_active_at=utcnow(),
        )
        db.add(workspace)
        db.flush()
        db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner", permissions=["*"]))

    settings = get_settings()
    provider = db.scalar(select(ModelProvider).where(ModelProvider.name == "火山方舟 OpenAI 兼容"))
    if not provider:
        provider = ModelProvider(
            owner_id=None,
            name="火山方舟 OpenAI 兼容",
            provider_type="openai_compatible",
            base_url=settings.ark_base_url,
            api_key_ref="mock" if settings.use_mock_llm else "env:ARK_API_KEY",
            default_model=settings.ark_endpoint_id or settings.ark_model or "doubao-seed-2-0-lite",
            supports_streaming=True,
            supports_embeddings=False,
            config={"source": "env", "api_key_env": "ARK_API_KEY"},
        )
        db.add(provider)
        db.flush()
        db.add(
            ModelConfig(
                provider_id=provider.id,
                name="默认豆包对话模型",
                model_id=provider.default_model,
                purpose="chat",
                context_window=128000,
                max_output_tokens=8192,
            )
        )
    else:
        provider.name = "火山方舟 OpenAI 兼容"
        provider.base_url = settings.ark_base_url
        provider.default_model = settings.ark_endpoint_id or settings.ark_model or provider.default_model
        if not settings.use_mock_llm:
            provider.api_key_ref = "env:ARK_API_KEY"
        default_config = db.scalar(
            select(ModelConfig).where(ModelConfig.provider_id == provider.id, ModelConfig.purpose == "chat")
        )
        if default_config:
            default_config.name = "默认豆包对话模型"
            default_config.model_id = provider.default_model

    if workspace and not db.scalar(select(McpServer).where(McpServer.workspace_id == workspace.id)):
        db.add(
            McpServer(
                owner_id=user.id,
                workspace_id=workspace.id,
                name="标准沙箱 MCP",
                transport="httpStream",
                url="http://localhost:8000/api/v1/sandboxes",
                enabled=True,
                health_status="online",
                tools=[
                    {"name": "sandbox.run", "description": "执行受控命令", "enabled": True},
                    {"name": "file.read", "description": "读取项目文件", "enabled": True},
                ],
            )
        )
    if workspace and not db.scalar(select(SandboxSession).where(SandboxSession.workspace_id == workspace.id)):
        db.add(
            SandboxSession(
                owner_id=user.id,
                workspace_id=workspace.id,
                name="默认演示沙箱",
                image="python:3.11-slim",
                status="ready",
                resource_limits={"cpu": "1", "memory": "1Gi", "timeout_seconds": 300},
            )
        )

    has_conversation = db.scalar(select(Conversation).where(Conversation.creator_id == user.id))
    if workspace:
        legacy_conversations = db.scalars(
            select(Conversation).where(Conversation.creator_id == user.id, Conversation.deleted_at.is_(None))
        ).all()
        for conversation in legacy_conversations:
            extra = dict(conversation.extra or {})
            if not extra.get("workspace_id"):
                extra["workspace_id"] = workspace.id
                extra.setdefault("category", "Default")
                extra.setdefault("folder", "Default")
                conversation.extra = extra
    if not has_conversation and agents:
        conv = Conversation(
            creator_id=user.id,
            chat_type="group",
            title="AgentHub 全栈协作组",
            description="演示多 Agent 拆解、执行、审查、预览和部署。",
            status="active",
            last_message_preview="欢迎进入 AgentHub，多 Agent 协作随时就绪。",
            last_message_sender="System",
            last_message_at=utcnow(),
            activity_score=88,
            extra={
                "workspace_id": workspace.id if workspace else None,
                "category": "Demo",
                "folder": "Factory",
                "remark": "Seeded AgentHub demo group",
            },
            message_count=1,
        )
        db.add(conv)
        db.flush()
        for agent in agents[:4]:
            db.add(
                ConversationParticipant(
                    conversation_id=conv.id,
                    participant_type="agent",
                    agent_id=agent.id,
                    role="member" if agent.type != "master" else "owner",
                )
            )
        db.add(
            Message(
                conversation_id=conv.id,
                sender_type="system",
                sender_name="System",
                content_type="event",
                content={"text": "会话已创建：主控、前端、后端和 Reviewer 已加入。"},
                status="completed",
            )
        )
    db.commit()
    db.refresh(user)
    return user
