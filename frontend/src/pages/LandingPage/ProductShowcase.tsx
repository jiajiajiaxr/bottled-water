import {
  ApiOutlined,
  AuditOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  FileTextOutlined,
  FunctionOutlined,
  MessageOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";

const chatMessages = [
  {
    author: "演示用户",
    text: "生成一份 AgentHub 发布方案，并给出可下载 PDF。",
    side: "user",
  },
  {
    author: "Writing Agent",
    text: "已整理章节、风险项和行动计划，正在调用 artifact.create_pdf。",
    side: "agent",
  },
  {
    author: "Reviewer",
    text: "审查通过：结构完整、产物可预览、导出入口可用。",
    side: "agent",
  },
];

const workflowNodes = [
  ["Start", "需求入口"],
  ["Agent", "Writing Worker"],
  ["Tool", "artifact.create_pdf"],
  ["Review", "Reviewer"],
  ["End", "产物交付"],
];

export function ProductShowcase() {
  return (
    <div className="landing-product-stack" aria-label="AgentHub 产品界面预览">
      <ChatPreview />
      <WorkflowPreview />
      <ArtifactPreview />
    </div>
  );
}

function ChatPreview() {
  return (
    <section className="landing-product-panel landing-chat-preview">
      <div className="landing-panel-top">
        <span className="landing-dot blue" />
        <span className="landing-panel-title">多 Agent 协作群</span>
        <span className="landing-panel-pill">
          <MessageOutlined /> 3 Agent
        </span>
      </div>
      <div className="landing-chat-body">
        <aside className="landing-chat-sidebar">
          {["发布方案", "文件总结", "代码审查"].map((item, index) => (
            <span className={index === 0 ? "active" : ""} key={item}>
              {item}
            </span>
          ))}
        </aside>
        <div className="landing-chat-thread">
          {chatMessages.map((message) => (
            <article className={`landing-chat-bubble ${message.side}`} key={message.author}>
              <strong>{message.author}</strong>
              <p>{message.text}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function WorkflowPreview() {
  return (
    <section className="landing-product-panel landing-workflow-preview">
      <div className="landing-panel-top">
        <span className="landing-dot cyan" />
        <span className="landing-panel-title">Workflow Canvas</span>
        <span className="landing-panel-pill">
          <PlayCircleOutlined /> running
        </span>
      </div>
      <div className="landing-workflow-grid">
        {workflowNodes.map(([type, label], index) => (
          <div className="landing-flow-node" key={label}>
            <span>{type}</span>
            <strong>{label}</strong>
            {index < workflowNodes.length - 1 && <i aria-hidden="true" />}
          </div>
        ))}
      </div>
    </section>
  );
}

function ArtifactPreview() {
  return (
    <section className="landing-product-panel landing-artifact-preview">
      <div className="landing-panel-top">
        <span className="landing-dot violet" />
        <span className="landing-panel-title">产物预览</span>
        <span className="landing-panel-pill">
          <FileTextOutlined /> PDF
        </span>
      </div>
      <div className="landing-artifact-page">
        <div>
          <h3>AgentHub 发布方案</h3>
          <p>多智能体协作平台 · 正式文档预览</p>
        </div>
        <ul>
          <li>
            <CheckCircleOutlined /> 真实 PDF / DOCX 导出
          </li>
          <li>
            <CloudUploadOutlined /> 文件上下文与工作区文件树
          </li>
          <li>
            <CodeOutlined /> 会话沙箱运行代码块
          </li>
          <li>
            <AuditOutlined /> 工具调用审计记录
          </li>
          <li>
            <ApiOutlined /> MCP / Skill / Tool 扩展
          </li>
          <li>
            <BranchesOutlined /> Dify 风格工作流编排
          </li>
        </ul>
        <div className="landing-artifact-footer">
          <span>
            <FunctionOutlined /> artifact.create_pdf
          </span>
          <span>ready</span>
        </div>
      </div>
    </section>
  );
}

