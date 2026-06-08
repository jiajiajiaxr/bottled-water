import type { ReactNode } from "react";
import {
  AppstoreOutlined,
  BranchesOutlined,
  MessageOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";

export type ProductModule = {
  title: string;
  description: string;
  points: string[];
  icon: ReactNode;
};

export type JourneyEntry = {
  role: string;
  entry: string;
  path: string;
  outcome: string;
};

export type CapabilityRow = {
  domain: string;
  console: string;
  backend: string;
  outcome: string;
};

export type WorkflowNodeDoc = {
  type: string;
  purpose: string;
  config: string;
  output: string;
};

export type LifecycleEntry = {
  title: string;
  detail: string;
};

export const productModules: ProductModule[] = [
  {
    title: "IM 工作台",
    description:
      "以会话为主入口，把需求、附件、Agent 回复、工具摘要和产物卡片放在同一条协作时间线中。",
    points: ["默认 Daily 单聊", "群聊自动组织", "消息流式回填", "右侧产物预览"],
    icon: <MessageOutlined />,
  },
  {
    title: "能力控制台",
    description:
      "统一管理 Agent、模型、工具、Skill、MCP 与知识库，先配置能力，再在会话或画布中授权使用。",
    points: ["Agent 广场", "模型 API", "工具目录", "Skill / MCP"],
    icon: <AppstoreOutlined />,
  },
  {
    title: "工作流运行时",
    description:
      "复杂群聊可由 Team Leader 动态调度；启用 workflow 后以画布为事实来源，运行态写入 WorkflowRun。",
    points: ["Team Leader 计划", "节点编排", "条件分支", "运行历史"],
    icon: <BranchesOutlined />,
  },
  {
    title: "治理与交付",
    description:
      "文件、产物、部署、沙箱和审计都落在工作区边界内，敏感操作由后端权限与日志兜底。",
    points: ["文件隔离", "版本 Diff", "部署回滚", "审计日志"],
    icon: <SafetyCertificateOutlined />,
  },
];

export const journeyEntries: JourneyEntry[] = [
  {
    role: "业务演示用户",
    entry: "演示登录 / 工作台",
    path: "创建工作区 -> 新建会话 -> 上传需求 -> 查看 Agent 回复和产物",
    outcome: "快速跑通需求分析、文档生成、审查和预览闭环。",
  },
  {
    role: "Agent 配置者",
    entry: "Agent 广场",
    path: "创建 Agent -> 绑定模型、工具、Skill、MCP -> 测试 -> 用于单聊或群聊",
    outcome: "把角色提示词和可调用能力变成可复用的团队成员。",
  },
  {
    role: "平台管理员",
    entry: "全局设置 / 平台控制",
    path: "配置模型供应商 -> 注册 MCP -> 管理沙箱和远程连接 -> 查看审计",
    outcome: "控制高权限能力、凭证和运行记录，降低演示环境风险。",
  },
  {
    role: "开发维护者",
    entry: "API 与源码地图",
    path: "查看 API 模块 -> 修改服务层 -> 补测试 -> 通过前后端验证",
    outcome: "按项目边界扩展工具、节点、文件格式和接口能力。",
  },
];

export const capabilityRows: CapabilityRow[] = [
  {
    domain: "账号、模型与设置",
    console: "全局设置：账号、模型 API、模型测试",
    backend: "auth.py / models.py / llm_gateway.py",
    outcome: "用户登录后可选择真实模型或 mock 模式，API Key 不暴露到前端。",
  },
  {
    domain: "工作区与项目文件",
    console: "工作区抽屉、平台控制、文件树",
    backend: "workspaces.py / workspace_files.py / files/",
    outcome: "会话、文件、产物、工具和运行记录按工作区隔离。",
  },
  {
    domain: "会话与消息",
    console: "会话列表、聊天区、成员管理、后台任务按钮",
    backend: "conversations.py / messages.py / realtime/",
    outcome: "支持默认 Daily 单聊、手动多 Agent 群聊、流式回复、协作进度、停止生成和重试。",
  },
  {
    domain: "Agent 与能力授权",
    console: "Agent 广场、工具目录、Skill、MCP",
    backend: "agents.py / tools.py / skills.py / mcp.py",
    outcome: "每个 Agent 独立绑定模型、工具、Skill、MCP 和 agentic loop 权限。",
  },
  {
    domain: "工作流画布",
    console: "会话设置里的画布、独立 Workflow Studio",
    backend: "workflows/engine.py / workflows/nodes/",
    outcome: "启用 workflow 后群聊按节点和边执行，并记录 WorkflowRun、节点输出和失败状态。",
  },
  {
    domain: "文件、知识库与上下文",
    console: "输入框附件、文件预览、知识库检索",
    backend: "files.py / knowledge.py / context/",
    outcome: "上传文件进入消息上下文，知识库检索结果可注入 Agent 推理。",
  },
  {
    domain: "产物、导出与部署",
    console: "产物卡片、右侧 PreviewPanel、部署记录",
    backend: "artifacts.py / artifact_exports.py / deployments.py",
    outcome: "支持 HTML、PDF、DOCX、XLSX、PPTX 等预览、版本、Diff 和导出。",
  },
  {
    domain: "安全、沙箱与审计",
    console: "平台控制：沙箱、远程连接、安全审计",
    backend: "sandbox.py / security_ops.py / audit.py",
    outcome: "高风险操作由后端权限校验、工作区目录隔离和审计日志约束。",
  },
];

export const workflowNodeDocs: WorkflowNodeDoc[] = [
  {
    type: "start",
    purpose: "接收用户输入、附件摘要和会话上下文。",
    config: "input_types",
    output: "标准化输入，作为后续节点变量来源。",
  },
  {
    type: "agent",
    purpose: "调用指定 Agent 的 Function Call Loop。",
    config: "agent_id",
    output: "Agent 回复、工具摘要、可选产物引用。",
  },
  {
    type: "tool",
    purpose: "调用后端工具目录中的内置或自定义工具。",
    config: "tool_name / arguments / agent_id",
    output: "工具执行结果、错误信息和审计记录。",
  },
  {
    type: "skill",
    purpose: "运行指定 Skill 包或 prompt skill。",
    config: "skill_id / arguments",
    output: "Skill 输出、运行状态和依赖检查结果。",
  },
  {
    type: "mcp",
    purpose: "调用 MCP 服务暴露的外部工具。",
    config: "mcp_server_id / tool_name / arguments",
    output: "MCP tool result、调用记录和失败原因。",
  },
  {
    type: "condition",
    purpose: "根据表达式或节点输出选择后续路径。",
    config: "expression / branches",
    output: "matched_branch 与命中路径。",
  },
  {
    type: "loop",
    purpose: "对一组节点执行有限循环。",
    config: "max_iterations",
    output: "current_iteration、循环输出和停止原因。",
  },
  {
    type: "review",
    purpose: "绑定 Reviewer 类 Agent 做审查、验收或安全检查。",
    config: "agent_id / criteria",
    output: "审查结论、问题列表和建议动作。",
  },
  {
    type: "artifact",
    purpose: "生成文档、表格、PPT、HTML 或 Web App 产物。",
    config: "artifact_type / title / source",
    output: "Artifact 记录、预览地址和导出入口。",
  },
  {
    type: "end",
    purpose: "汇总前序节点输出，形成最终回复。",
    config: "summary_template",
    output: "最终 assistant message 和 workflow 完成态。",
  },
];

export const assetLifecycleEntries: LifecycleEntry[] = [
  {
    title: "1. 上传与归档",
    detail:
      "文件通过输入框或工作区文件树进入后端，落在当前工作区目录下，并生成 FileAsset 或工作区文件节点。",
  },
  {
    title: "2. 抽取与预览",
    detail:
      "PDF、Office、Markdown、HTML、文本和图片会走不同 previewer；Office 优先转 PDF，失败时降级为文本 PDF。",
  },
  {
    title: "3. 上下文注入",
    detail:
      "发送消息时，附件摘要、知识库片段、会话记忆和工作区变量会组合成 Agent 可读上下文。",
  },
  {
    title: "4. 工具执行",
    detail:
      "Agent 根据权限调用 file、artifact、sandbox、api.test 等工具，后端校验 schema、权限和路径。",
  },
  {
    title: "5. 产物生成",
    detail:
      "文档、表格、PPT、HTML 和 Web App 产物写入 Artifact，并保留版本、源内容和真实文件路径。",
  },
  {
    title: "6. 交付与回滚",
    detail:
      "用户可在 PreviewPanel 中预览、编辑、Diff、导出，Web 类产物还可创建部署预览和回滚记录。",
  },
];
