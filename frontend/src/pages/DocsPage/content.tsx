import type { ReactNode } from "react";
import {
  ApiOutlined,
  AppstoreOutlined,
  AuditOutlined,
  BookOutlined,
  BranchesOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  MessageOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from "@ant-design/icons";

export type NavGroup = {
  title: string;
  links: Array<{
    title: string;
    href: string;
  }>;
};

export type IconCard = {
  id?: string;
  title: string;
  description: string;
  icon: ReactNode;
};

export type ApiEntry = {
  id: string;
  title: string;
  meta: string;
  icon: ReactNode;
};

export type EndpointEntry = {
  module: string;
  endpoint: string;
  purpose: string;
};

export type RuntimeEntry = {
  name: string;
  usage: string;
  boundary: string;
};

export const navGroups: NavGroup[] = [
  {
    title: "快速开始",
    links: [
      { title: "首次登录", href: "#start" },
      { title: "本地启动", href: "#local" },
      { title: "工作区配置", href: "#workspace" },
      { title: "首次运行会话", href: "#first-run" },
      { title: "后台任务与用量", href: "#usage" },
    ],
  },
  {
    title: "模型与运行",
    links: [
      { title: "模型供应商", href: "#models" },
      { title: "Reasoning 与流式输出", href: "#reasoning" },
      { title: "队列与重试", href: "#queue" },
      { title: "错误码与排查", href: "#errors" },
    ],
  },
  {
    title: "API 文档",
    links: [
      { title: "API 总览", href: "#api-overview" },
      { title: "认证与用户", href: "#api-auth" },
      { title: "工作区 / 会话 / 消息", href: "#api-chat" },
      { title: "Agent / Tool / MCP", href: "#api-capability" },
      { title: "文件 / 知识库 / 产物", href: "#api-assets" },
      { title: "工作流运行", href: "#api-workflow" },
    ],
  },
  {
    title: "集成扩展",
    links: [
      { title: "AI Coding 工具", href: "#integration" },
      { title: "自定义工具", href: "#custom-tools" },
      { title: "Skill 包", href: "#skills" },
      { title: "MCP 服务", href: "#mcp" },
    ],
  },
  {
    title: "使用指南",
    links: [
      { title: "文件与知识库", href: "#files" },
      { title: "多 Agent 协作", href: "#collaboration" },
      { title: "产物预览与导出", href: "#artifacts" },
      { title: "部署预览", href: "#deploy" },
      { title: "权限与审计", href: "#security" },
      { title: "常见问题", href: "#faq" },
      { title: "更新日志", href: "#updates" },
    ],
  },
];

export const quickEntries: IconCard[] = [
  {
    title: "快速开始",
    description: "从演示用户进入 IM 工作台，完成第一条多 Agent 会话",
    icon: <ThunderboltOutlined />,
  },
  {
    title: "控制台",
    description: "管理工作区、模型、Agent、Skill、MCP 与工具目录",
    icon: <AppstoreOutlined />,
  },
  {
    title: "API 文档",
    description: "查看认证、会话、消息、Agent 和产物接口边界",
    icon: <ApiOutlined />,
  },
  {
    title: "AI Coding 工具配置",
    description: "理解工具、Skill、MCP 和沙箱执行链路",
    icon: <CodeOutlined />,
  },
  {
    title: "运行机制",
    description: "阅读单聊、群聊、画布优先编排和流式事件",
    icon: <BranchesOutlined />,
  },
  {
    title: "常见问题",
    description: "定位登录、模型、文件、工作流和部署相关问题",
    icon: <BookOutlined />,
  },
];

export const capabilitySections: IconCard[] = [
  {
    id: "chat",
    title: "会话工作台",
    description:
      "会话是 AgentHub 的主入口。左侧管理会话与分类，中间承载流式消息，右侧按需打开产物预览。",
    icon: <MessageOutlined />,
  },
  {
    id: "agents",
    title: "Agent 广场",
    description:
      "官方 Agent 与自定义 Agent 使用同一套模型、工具、Skill、MCP 权限配置，单聊时直接进入对应 Agent 的执行循环。",
    icon: <RobotOutlined />,
  },
  {
    id: "workflow",
    title: "工作流画布",
    description:
      "群聊以 workflow 作为事实来源，节点支持 agent、tool、skill、mcp、condition、loop、review、artifact 与 end。",
    icon: <BranchesOutlined />,
  },
  {
    id: "artifacts",
    title: "文件与产物",
    description:
      "文件上传后进入消息上下文；产物支持预览、修订、Diff 与 PDF、DOCX、XLSX、PPTX、HTML 等导出。",
    icon: <FileTextOutlined />,
  },
];

export const apiSections: ApiEntry[] = [
  {
    id: "api-auth",
    title: "认证与用户",
    meta: "backend/app/api/auth.py",
    icon: <SafetyCertificateOutlined />,
  },
  {
    id: "api-chat",
    title: "会话与消息",
    meta: "backend/app/api/conversations.py / messages.py",
    icon: <MessageOutlined />,
  },
  {
    id: "api-capability",
    title: "Agent / Tool / MCP",
    meta: "backend/app/api/agents.py / tools.py / mcp.py",
    icon: <ToolOutlined />,
  },
  {
    id: "api-assets",
    title: "文件 / 知识库 / 产物",
    meta: "backend/app/api/files.py / knowledge.py / artifacts.py",
    icon: <FileProtectOutlined />,
  },
  {
    id: "api-workflow",
    title: "工作流运行",
    meta: "backend/app/api/conversations.py / workflow.py",
    icon: <BranchesOutlined />,
  },
];

export const maintainCards: IconCard[] = [
  {
    id: "sandbox",
    title: "权限与审计",
    description: "RBAC、审计日志和高风险能力都由后端统一控制，前端只触发授权后的操作。",
    icon: <AuditOutlined />,
  },
  {
    id: "deploy",
    title: "部署预览",
    description: "HTML/Web App、文档和表格类产物可生成预览记录，并保留导出与回滚入口。",
    icon: <DeploymentUnitOutlined />,
  },
  {
    title: "数据边界",
    description: "工作区隔离会话、文件、工具、Skill、MCP 与运行记录，减少跨项目上下文污染。",
    icon: <DatabaseOutlined />,
  },
];

export const runtimeEntries: RuntimeEntry[] = [
  {
    name: "mock",
    usage: "无外部模型密钥时的本地演示与前端联调",
    boundary: "不会访问真实供应商，适合验收 UI、路由和基础编排链路。",
  },
  {
    name: "ark",
    usage: "接入火山方舟或兼容 OpenAI 的真实推理服务",
    boundary: "密钥只由后端读取，前端不保存 API Key。",
  },
  {
    name: "auto",
    usage: "根据环境变量自动选择真实模型或 mock 模式",
    boundary: "适合团队共享开发环境，缺少密钥时仍可进入演示闭环。",
  },
];

export const endpointEntries: EndpointEntry[] = [
  { module: "认证", endpoint: "/api/v1/auth/login", purpose: "登录、演示登录、会话恢复" },
  { module: "工作区", endpoint: "/api/v1/workspaces", purpose: "工作区隔离、成员、项目文件入口" },
  { module: "会话", endpoint: "/api/v1/conversations", purpose: "单聊、群聊、分类、归档、工作流保存" },
  { module: "消息", endpoint: "/api/v1/messages", purpose: "消息发送、流式事件、停止生成、重试" },
  { module: "Agent", endpoint: "/api/v1/agents", purpose: "官方 Agent、自定义 Agent、权限绑定" },
  { module: "工具", endpoint: "/api/v1/tools", purpose: "内置工具、自定义工具、AI 生成工具、调用测试" },
  { module: "MCP", endpoint: "/api/v1/mcp", purpose: "服务注册、探测、工具调用、调用记录" },
  { module: "文件", endpoint: "/api/v1/files", purpose: "上传、解析、预览、摘要、向量化入口" },
  { module: "产物", endpoint: "/api/v1/artifacts", purpose: "产物创建、版本、Diff、预览、导出" },
  { module: "任务", endpoint: "/api/v1/tasks", purpose: "后台任务、取消、刷新、运行态展示" },
];

export const integrationSteps = [
  "在全局设置里确认模型供应商、工具目录、Skill 和 MCP 服务状态。",
  "进入 Agent 广场，为目标 Agent 绑定允许调用的工具、Skill 或 MCP。",
  "在单聊中直接验证 Agent 小循环，或在群聊画布中把能力节点接入 workflow。",
  "运行后查看消息、工具摘要、后台任务、审计日志和产物预览。",
];

export const troubleshootingRows = [
  ["登录失败", "检查 auth API、token、本地存储和后端环境变量。"],
  ["模型无响应", "检查 LLM_PROVIDER、ARK_API_KEY、模型配置和后端日志。"],
  ["消息不流式", "检查 SSE/WebSocket、event_bus、messages API 和前端消息 Store。"],
  ["Agent 不调用工具", "检查 Agent 权限、tool_loop、工具 schema 和调用参数。"],
  ["工作流不运行", "检查 conversation.extra.workflow、节点类型、边和 workflow run 状态。"],
  ["产物打不开", "检查 artifact 文件路径、预览 URL、导出格式和浏览器控制台错误。"],
];

export const localBootCode = `cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app:app --reload --reload-dir ./app

cd ../frontend
pnpm install
pnpm dev`;

export const apiExampleCode = `const conversation = await api.createConversation({
  workspace_id: activeWorkspaceId,
  chat_type: "single",
  title: "需求评审",
  participant_agent_ids: ["agent-reviewer"]
});

await api.sendMessage(conversation.id, {
  content: "请审查这份需求文档，并生成可执行任务清单。",
  attachments: [uploadedFile]
});`;

export const workflowExampleCode = `{
  "nodes": [
    { "id": "start", "type": "start", "title": "接收任务" },
    { "id": "agent-reviewer", "type": "agent", "title": "Reviewer" },
    { "id": "artifact", "type": "artifact", "title": "生成评审报告" },
    { "id": "end", "type": "end", "title": "汇总输出" }
  ],
  "edges": [
    ["start", "agent-reviewer"],
    ["agent-reviewer", "artifact"],
    ["artifact", "end"]
  ]
}`;

export const updateItems = [
  "新增公开 /docs 文档站，控制台顶部可一键进入。",
  "补充工作流画布独立页面与嵌入式运行视图。",
  "工具、Skill、MCP 模块完成目录边界拆分，旧入口保留兼容 shim。",
];
