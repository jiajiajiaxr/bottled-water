import type {
  Agent,
  ChatMessage,
  Conversation,
  Deployment,
  KnowledgeBase,
  McpServer,
  ModelConfig,
  ModelProvider,
  Project,
  RemoteConnection,
  SandboxSession,
  Skill,
  UploadedFile,
  User,
  Workspace,
  WorkspaceArtifact
} from "./types";

export const demoUser: User = {
  id: "demo-user",
  name: "演示用户",
  role: "demo",
  avatar: "演"
};

export const demoConversations: Conversation[] = [
  {
    id: "conv-product",
    chat_type: "group",
    title: "官网落地页生成",
    participants: [
      { id: "p1", participant_type: "agent", agent_id: "agent-design", agent_name: "Design Agent", agent_type: "frontend", agent_status: "online", role: "owner" },
      { id: "p2", participant_type: "agent", agent_id: "agent-deploy", agent_name: "Deploy Agent", agent_type: "deploy", agent_status: "online", role: "member" }
    ],
    participant_count: 2,
    agent_count: 2,
    user_count: 1,
    updatedAt: new Date().toISOString(),
    pinned: true,
    archived: false,
    unread: 2,
    tags: ["群聊", "前端"],
    lastMessage: "已生成首屏结构，右侧可预览和调整代码。"
  },
  {
    id: "conv-api",
    chat_type: "single",
    title: "API 接入排查",
    participants: [{ id: "p3", participant_type: "agent", agent_id: "agent-backend", agent_name: "Backend Agent", agent_type: "backend", agent_status: "online", role: "owner" }],
    participant_count: 1,
    agent_count: 1,
    user_count: 1,
    updatedAt: new Date(Date.now() - 1000 * 60 * 46).toISOString(),
    pinned: false,
    archived: false,
    unread: 0,
    tags: ["接口"],
    lastMessage: "建议统一从 /api/v1 代理请求。"
  },
  {
    id: "conv-archive",
    chat_type: "group",
    title: "旧版插件迁移",
    participants: [{ id: "p4", participant_type: "agent", agent_id: "agent-migration", agent_name: "Migration Agent", agent_type: "custom", agent_status: "offline", role: "member" }],
    participant_count: 1,
    agent_count: 1,
    user_count: 1,
    updatedAt: new Date(Date.now() - 1000 * 60 * 60 * 24 * 2).toISOString(),
    pinned: false,
    archived: true,
    unread: 0,
    tags: ["归档"],
    lastMessage: "迁移记录已归档。"
  }
];

export const demoMessages: Record<string, ChatMessage[]> = {
  "conv-product": [
    {
      id: "m1",
      conversationId: "conv-product",
      role: "system",
      kind: "event",
      author: "AgentHub",
      content: "会话已创建，已邀请 Design Agent 与 Deploy Agent。",
      createdAt: new Date(Date.now() - 1000 * 60 * 28).toISOString()
    },
    {
      id: "m2",
      conversationId: "conv-product",
      role: "user",
      kind: "text",
      author: "演示用户",
      content: "帮我做一个能展示 AgentHub 能力的 IM 工作台。",
      createdAt: new Date(Date.now() - 1000 * 60 * 25).toISOString()
    },
    {
      id: "m3",
      conversationId: "conv-product",
      role: "assistant",
      kind: "code",
      author: "Design Agent",
      content: "已搭建三栏工作区：左侧会话、中间消息流、右侧预览与部署。",
      createdAt: new Date(Date.now() - 1000 * 60 * 23).toISOString(),
      streamState: "done"
    }
  ],
  "conv-api": [
    {
      id: "m4",
      conversationId: "conv-api",
      role: "assistant",
      kind: "text",
      author: "Backend Agent",
      content: "当前前端会请求 /api/v1，并在本地开发时由 Vite 代理到 localhost:8000。",
      createdAt: new Date(Date.now() - 1000 * 60 * 44).toISOString()
    }
  ],
  "conv-archive": [
    {
      id: "m5",
      conversationId: "conv-archive",
      role: "tool",
      kind: "event",
      author: "Migration Agent",
      content: "迁移任务已完成并归档。",
      createdAt: new Date(Date.now() - 1000 * 60 * 60 * 24 * 2).toISOString()
    }
  ]
};

export const demoArtifact: WorkspaceArtifact = {
  id: "artifact-main",
  conversationId: "conv-product",
  title: "LandingPreview.tsx",
  language: "tsx",
  code: `<section className="landing">
  <h1>AgentHub</h1>
  <p>多 Agent 协作、即时预览、持续部署的一体化工作台。</p>
  <button>开始演示</button>
</section>`,
  previousCode: `<section>
  <h1>AgentHub</h1>
  <p>多 Agent 协作工作台。</p>
</section>`,
  previewUrl: "about:blank",
  updatedAt: new Date().toISOString()
};

export const demoDeployment: Deployment = {
  id: "deploy-demo",
  status: "ready",
  url: "https://agenthub-demo.local",
  commit: "demo-7f4a2c1",
  updatedAt: new Date().toISOString()
};

export const demoAgents: Agent[] = [
  {
    id: "agent-master",
    name: "Master Agent",
    display_name: "Master Agent",
    type: "master",
    version: "1.0",
    avatar_color: "#1677ff",
    capabilities: [
      { label: "调度", category: "编排", proficiency: 5 },
      { label: "拆解", category: "编排", proficiency: 5 }
    ],
    description: "负责需求研判、任务拆解、调度与成果聚合。",
    status: "online",
    provider: "ark",
    is_official: true,
    response_latency_ms: 900,
    config: { supports_streaming: true, supports_file_upload: true, tools: ["file.extract_text", "file.summarize", "artifact.export"] }
  },
  {
    id: "agent-frontend",
    name: "Frontend Worker",
    display_name: "Frontend Worker",
    type: "frontend",
    version: "1.0",
    avatar_color: "#059669",
    capabilities: [
      { label: "前端", category: "编码", proficiency: 5 },
      { label: "React", category: "编码", proficiency: 5 },
      { label: "UI", category: "设计", proficiency: 4 }
    ],
    description: "React、TypeScript、Ant Design 与交互实现专家。",
    status: "online",
    provider: "ark",
    is_official: true,
    response_latency_ms: 880,
    config: { supports_streaming: true, supports_file_upload: true, tools: ["file.read", "file.write", "artifact.create_web_app", "sandbox.run", "browser.preview"] }
  },
  {
    id: "agent-backend",
    name: "Backend Worker",
    display_name: "Backend Worker",
    type: "backend",
    version: "1.0",
    avatar_color: "#7c3aed",
    capabilities: [
      { label: "后端", category: "编码", proficiency: 5 },
      { label: "API", category: "架构", proficiency: 5 },
      { label: "数据库", category: "架构", proficiency: 4 }
    ],
    description: "FastAPI、SQLAlchemy、PostgreSQL 与实时服务专家。",
    status: "online",
    provider: "ark",
    is_official: true,
    response_latency_ms: 920,
    config: { supports_streaming: true, supports_file_upload: true, tools: ["file.read", "file.write", "db.inspect", "sandbox.run", "api.test"] }
  }
];

export const demoFiles: UploadedFile[] = [];

export const demoKnowledgeBases: KnowledgeBase[] = [
  {
    id: "kb-demo",
    name: "AgentHub 产品知识库",
    description: "演示 PRD、API、验收标准等资料。",
    scope: "workspace",
    visibility: "private",
    document_count: 3,
    chunk_count: 28,
    total_tokens: 12000,
    status: "ready"
  }
];

export const demoWorkspaces: Workspace[] = [
  {
    id: "workspace-demo",
    name: "默认全栈工作区",
    description: "预置全链路开发模板，挂载主控、前端、后端、Reviewer 和部署资源。",
    type: "vertical",
    status: "active",
    tags: ["默认", "全链路开发"],
    member_count: 1,
    project_count: 1,
    workflow: { mode: "hybrid" }
  }
];

export const demoProjects: Project[] = [
  {
    id: "project-demo",
    workspace_id: "workspace-demo",
    name: "AgentHub 演示项目",
    description: "用于答辩演示的项目资产。",
    type: "code_project",
    status: "active",
    tags: ["demo"],
    file_count: 2,
    current_version: 1
  }
];

export const demoModelProviders: ModelProvider[] = [
  {
    id: "provider-ark-openai",
    name: "火山方舟 OpenAI 兼容",
    provider_type: "openai-compatible",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    default_model: "doubao-seed-2-0-lite",
    supports_streaming: true,
    supports_embeddings: false,
    status: "active",
    config: { secret_mode: "environment" },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
];

export const demoModelConfigs: ModelConfig[] = [
  {
    id: "model-default-chat",
    provider_id: "provider-ark-openai",
    provider_name: "火山方舟 OpenAI 兼容",
    name: "主控/聊天默认模型",
    model_id: "doubao-seed-2-0-lite",
    purpose: "chat",
    context_window: 128000,
    max_output_tokens: 4096,
    temperature_default: 0.4,
    config: { route: "master,worker,reviewer,summary" },
    status: "active",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
];

export const demoMcpServers: McpServer[] = [
  {
    id: "mcp-sandbox",
    workspace_id: "workspace-demo",
    name: "标准沙箱 MCP",
    transport: "stdio",
    command: "agenthub-mcp-sandbox",
    args: ["--workspace", "workspace-demo"],
    enabled: true,
    health_status: "online",
    tools: [
      { name: "sandbox.run", description: "执行受控命令", enabled: true },
      { name: "file.read", description: "读取工作区文件", enabled: true },
      { name: "browser.open", description: "打开预览页面", enabled: true }
    ],
    tool_filter: ["sandbox.*", "file.*", "browser.*"],
    timeout_ms: 30000,
    retry: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
];

export const demoSkills: Skill[] = [
  {
    id: "skill-frontend-review",
    workspace_id: "workspace-demo",
    name: "前端审查 Skill",
    description: "检查 React 页面交互、样式一致性、附件展示和预览链路。",
    category: "quality",
    scope: "workspace",
    version: "1.0.0",
    enabled: true,
    source: "manual",
    prompt_template: "请以资深前端 reviewer 视角审查当前产物，列出阻塞问题和可验证修复建议。",
    tools: ["file.read", "browser.open", "sandbox.run"],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  },
  {
    id: "skill-mcp-sandbox",
    workspace_id: "workspace-demo",
    name: "沙箱 MCP Skill",
    description: "从标准沙箱 MCP 导入的命令执行与文件读取能力。",
    category: "mcp",
    scope: "workspace",
    version: "1.0.0",
    enabled: true,
    source: "mcp",
    mcp_server_id: "mcp-sandbox",
    tools: ["sandbox.run", "file.read", "browser.open"],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
];

export const demoSandboxes: SandboxSession[] = [
  {
    id: "sandbox-demo",
    workspace_id: "workspace-demo",
    name: "默认演示沙箱",
    image: "python:3.11-node20",
    status: "ready",
    resource_limits: { cpu: "2", memory: "2Gi", timeout_seconds: 300 },
    command_history: [
      {
        command: "pytest -q",
        argv: ["pytest", "-q"],
        exit_code: 0,
        stdout: "[mock-sandbox] 11 passed",
        stderr: "",
        duration_ms: 840,
        created_at: new Date().toISOString()
      }
    ],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
];

export const demoRemoteConnections: RemoteConnection[] = [
  {
    id: "remote-browser-demo",
    workspace_id: "workspace-demo",
    name: "本地预览浏览器",
    connection_type: "browser",
    endpoint: "http://127.0.0.1:5173",
    status: "connected",
    capabilities: ["open", "screenshot", "inspect"],
    session_state: { active_tab: "http://127.0.0.1:5173", mode: "browser" },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  }
];
