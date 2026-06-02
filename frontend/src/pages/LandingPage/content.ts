export const githubUrl = "https://github.com/jiajiajiaxr/bottled-water";

export const capabilities = [
  {
    title: "会话协作",
    eyebrow: "IM Workspace",
    problem: "多 Agent 项目最容易散在一堆任务、文件和日志里，答辩时很难讲清楚谁做了什么。",
    demo: "左侧会话、群聊成员、@Agent 指定回复、附件和历史消息会保持在一个可恢复的 IM 工作台里。",
    signals: ["单聊 / 群聊", "成员管理", "历史恢复"],
  },
  {
    title: "Agent Loop",
    eyebrow: "Function Call",
    problem: "如果 Agent 只是文字回复，工具、文件和产物都容易变成口头承诺。",
    demo: "每个 Worker 独立拿到授权工具，模型返回 tool_calls 后真实执行，再把结果回填生成最终回复。",
    signals: ["工具自主选择", "结果回填", "权限拒绝"],
  },
  {
    title: "工作流画布",
    eyebrow: "Canvas",
    problem: "群聊协作需要既能默认并行，也能被人工编排成项目流程。",
    demo: "会话绑定独立 workflow，支持节点、连线、运行态、AI 生成和 Agent 按画布执行。",
    signals: ["DAG 调度", "节点状态", "并行 Agent"],
  },
  {
    title: "工具执行",
    eyebrow: "Tool / Skill / MCP",
    problem: "本地工具、能力包和外部服务如果混在一起，后续会很难扩展和审计。",
    demo: "Tool、Skill、MCP 分层管理，执行层做参数校验、授权检查、调用记录和错误回传。",
    signals: ["工具目录", "Skill 包", "MCP Server"],
  },
  {
    title: "文件与产物",
    eyebrow: "Artifact Studio",
    problem: "用户需要看到真实文件，而不是 AI 在消息里说“已经生成”。",
    demo: "PDF、Word、PPT、Excel、HTML 产物进入聊天卡片和工作区文件树，可预览、下载和继续引用。",
    signals: ["真实二进制", "在线预览", "@file 引用"],
  },
  {
    title: "沙箱审计",
    eyebrow: "Safe Runtime",
    problem: "代码运行必须可控、可复现、可追踪，否则演示时一旦失败就没有解释路径。",
    demo: "sandbox.run、test.run 和聊天代码块都在会话沙箱执行，记录 stdout、stderr、exit_code 和耗时。",
    signals: ["工作区隔离", "运行记录", "安全策略"],
  },
];

export const metrics = [
  { value: "8+", label: "官方 Agent 类型" },
  { value: "30+", label: "Tool / Skill / MCP 能力" },
  { value: "10", label: "工作流节点类型" },
  { value: "9", label: "产物格式" },
  { value: "165+", label: "后端回归测试" },
];

export const productFlow = [
  { title: "用户发起任务", detail: "消息、附件、@Agent 和 @file 引用进入上下文。" },
  { title: "Agent 协作", detail: "单聊走 Worker Loop，群聊按会话 workflow 执行。" },
  { title: "调用能力", detail: "Tool / Skill / MCP 被模型选择并真实执行。" },
  { title: "生成产物", detail: "文件、产物卡片、预览和导出链接来自工具结果。" },
  { title: "审查交付", detail: "Reviewer 汇总风险，运行态和审计记录可追溯。" },
];

export const architectureModules = [
  ["LLM Gateway", "火山方舟与 OpenAI-compatible 统一入口，保留 tools / tool_choice / stream 语义。"],
  ["Agent Function Loop", "构建上下文、暴露授权 tools、执行 tool_calls、回填工具结果。"],
  ["Workflow Engine", "会话画布为事实来源，调度 Agent、Tool、Skill、MCP、Artifact 节点。"],
  ["Tool Runtime", "内置工具、自定义工具、Skill Runtime、MCP Adapter 分层执行。"],
  ["Artifact / File / Sandbox", "工作区文件树、真实产物生成、Office 转 PDF 预览、会话沙箱运行。"],
  ["Realtime Events", "SSE / WebSocket 推送消息 delta、节点状态、工具调用和全局结束事件。"],
];

export const scenarios = [
  {
    title: "生成 PDF 项目方案",
    prompt: "请生成一份 AgentHub 项目发布方案 PDF。",
    result: "Writing Agent 调用 artifact.create_pdf，聊天里出现真实 PDF 产物卡片。",
    tool: "artifact.create_pdf",
  },
  {
    title: "生成 HTML 应用",
    prompt: "做一个带交互逻辑的计算器 HTML 页面。",
    result: "Agent 生成完整 HTML / CSS / JS，右侧预览可直接运行。",
    tool: "artifact.create_html",
  },
  {
    title: "上传文件总结",
    prompt: "总结这个文件，并提取关键风险。",
    result: "file.extract_text 与 file.summarize 进入上下文，回复引用附件摘要。",
    tool: "file.extract_text",
  },
  {
    title: "多 Agent 审查",
    prompt: "Frontend、Backend、Reviewer 分别审查这个方案。",
    result: "群聊 workflow 并行执行多个 Agent，生成独立气泡和节点状态。",
    tool: "workflow.agent",
  },
  {
    title: "沙箱运行 Python",
    prompt: "运行这段 Python 代码并展示 stdout。",
    result: "聊天代码块按钮直接调用 sandbox.run，结果附着在代码块下方。",
    tool: "sandbox.run",
  },
];

export const stackItems = [
  "React 18",
  "TypeScript",
  "Vite",
  "Ant Design",
  "FastAPI",
  "SQLAlchemy",
  "PostgreSQL",
  "Redis",
  "uv",
  "Docker",
];

export const workflowCode = `{
  "settings": {
    "output_mode": "independent_messages"
  },
  "nodes": [
    { "id": "start", "type": "start" },
    {
      "id": "writing-agent",
      "type": "agent",
      "config": {
        "agent_id": "writing-worker",
        "input": "{{input}}\\n{{upstream.text}}",
        "tools": ["artifact.create_pdf", "file.summarize"]
      }
    },
    { "id": "review", "type": "review" },
    { "id": "end", "type": "end" }
  ]
}`;

