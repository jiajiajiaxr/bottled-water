export const githubUrl = "https://github.com/jiajiajiaxr/bottled-water";

export const capabilityCards = [
  {
    title: "多 Agent 群聊协作",
    kicker: "IM Workspace",
    body: "用会话组织任务、成员、附件和上下文，Agent 像团队成员一样独立发言、协作和审查。",
    points: ["单聊 / 群聊", "@Agent 指定", "历史可恢复"],
  },
  {
    title: "Agent Function Call Loop",
    kicker: "Agent Runtime",
    body: "每个 Worker 使用自己的模型、工具、Skill 和 MCP 权限，按工具结果继续推理，而不是文字假装完成。",
    points: ["多轮工具回填", "权限校验", "产物卡片映射"],
  },
  {
    title: "Tool / Skill / MCP 扩展",
    kicker: "Capability Layer",
    body: "内置工具、自定义工具、Skill 包和外部 MCP Server 分层管理，支持测试、审计和授权。",
    points: ["工具目录", "Skill 包", "MCP 调用记录"],
  },
  {
    title: "工作流画布",
    kicker: "Workflow Engine",
    body: "以会话 workflow 为事实来源，支持节点、连线、运行态、输入输出映射和并行 Agent 回复。",
    points: ["DAG 执行", "节点状态", "AI 生成画布"],
  },
  {
    title: "文件系统与产物预览",
    kicker: "Artifact Studio",
    body: "上传、沙箱、产物和导出文件汇总到工作区文件树，PDF / Office / HTML 可预览和下载。",
    points: ["真实文件", "在线预览", "@file 引用"],
  },
  {
    title: "沙箱运行与审计",
    kicker: "Safe Execution",
    body: "代码块、工具命令和测试都在工作区会话沙箱内执行，保留 stdout、stderr、exit_code 和耗时。",
    points: ["会话隔离", "安全策略", "ToolInvocation"],
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
  "用户发起任务",
  "Master / Worker 协作",
  "调用 Tool / Skill / MCP",
  "生成文件与产物",
  "Reviewer 审查",
  "预览 / 导出 / 部署",
];

export const architectureModules = [
  {
    title: "LLM Gateway",
    body: "统一火山方舟和 OpenAI-compatible 接入，工具参数与流式事件按协议转换。",
  },
  {
    title: "Agent Loop",
    body: "构建上下文、暴露授权 tools、执行 tool_calls、回填结果并生成最终回复。",
  },
  {
    title: "Workflow Engine",
    body: "编译会话画布，调度串行、并行、条件、产物和审查节点。",
  },
  {
    title: "Tool Runtime",
    body: "内置工具、自定义 Python、Skill、MCP 分发执行，记录调用和权限结果。",
  },
  {
    title: "Artifact / File / Sandbox",
    body: "工作区目录隔离，真实生成 PDF / Office / HTML，沙箱可运行代码和测试。",
  },
  {
    title: "Realtime SSE / WebSocket",
    body: "推送 message delta、node state、tool event、workflow completed 和取消事件。",
  },
];

export const scenarioCards = [
  "生成 PDF 项目方案",
  "构建 HTML 页面",
  "上传文件并总结",
  "多 Agent 审查代码",
  "工作流自动编排",
];

export const codeExample = `{
  "node": "artifact-report",
  "type": "agent",
  "agent_id": "writing-agent",
  "config": {
    "input": "{{input}}\\n{{upstream.text}}",
    "tools": ["artifact.create_pdf", "file.summarize"],
    "output_mode": "preview_card"
  }
}`;

