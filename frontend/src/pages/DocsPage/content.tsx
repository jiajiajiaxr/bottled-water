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

export const navGroups: NavGroup[] = [
  {
    title: "快速开始",
    links: [
      { title: "首次登录", href: "#start" },
      { title: "本地启动", href: "#local" },
      { title: "工作区配置", href: "#workspace" },
      { title: "演示链路", href: "#demo-flow" },
    ],
  },
  {
    title: "核心能力",
    links: [
      { title: "会话工作台", href: "#chat" },
      { title: "Agent 广场", href: "#agents" },
      { title: "工作流画布", href: "#workflow" },
      { title: "文件与产物", href: "#artifacts" },
    ],
  },
  {
    title: "API 文档",
    links: [
      { title: "认证与用户", href: "#api-auth" },
      { title: "会话与消息", href: "#api-chat" },
      { title: "Agent / Tool / MCP", href: "#api-capability" },
    ],
  },
  {
    title: "运维安全",
    links: [
      { title: "权限与审计", href: "#security" },
      { title: "沙箱与远程", href: "#sandbox" },
      { title: "部署预览", href: "#deploy" },
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

