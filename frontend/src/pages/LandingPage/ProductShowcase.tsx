import {
  ApiOutlined,
  AuditOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  FileTextOutlined,
  FunctionOutlined,
  MessageOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

const agentMessages = [
  ["演示用户", "生成一份项目发布方案，输出 PDF，并让 Reviewer 审查。", "user"],
  ["Writing Agent", "已读取需求，准备结构化 content_model 并调用 artifact.create_pdf。", "agent"],
  ["Reviewer", "审查通过：章节完整，风险项和交付步骤清晰。", "agent"],
];

const workflowNodes = [
  ["Start", "需求入口"],
  ["Agent", "Writing Worker"],
  ["Tool", "artifact.create_pdf"],
  ["Review", "Reviewer"],
  ["End", "交付"],
];

export function ProductShowcase() {
  return (
    <div className="landing-product-stage" aria-label="AgentHub 产品界面叠层预览">
      <WorkbenchMock />
      <WorkflowLayer />
      <ArtifactLayer />
      <ToolRunLayer />
    </div>
  );
}

function WorkbenchMock() {
  return (
    <section className="landing-workbench-window">
      <div className="landing-window-top">
        <span className="landing-brand-dot">AH</span>
        <strong>AgentHub Workbench</strong>
        <span>默认全栈工作区</span>
      </div>
      <div className="landing-workbench-grid">
        <aside className="landing-workbench-sidebar">
          <span className="active">发布方案协作群</span>
          <span>HTML 应用构建</span>
          <span>文件总结与风险</span>
          <span>代码审查流水线</span>
        </aside>
        <main className="landing-workbench-chat">
          <div className="landing-chat-title">
            <div>
              <strong>发布方案协作群</strong>
              <p>Writing Agent · Backend Worker · Reviewer</p>
            </div>
            <button type="button">工作流画布</button>
          </div>
          <div className="landing-message-thread">
            {agentMessages.map(([author, text, role]) => (
              <article className={`landing-message ${role}`} key={author}>
                <strong>{author}</strong>
                <p>{text}</p>
              </article>
            ))}
            <article className="landing-preview-card-mini">
              <FileTextOutlined />
              <div>
                <strong>预览产物：项目发布方案.pdf</strong>
                <p>已生成真实 PDF，可预览、下载和继续修订。</p>
              </div>
            </article>
          </div>
        </main>
      </div>
    </section>
  );
}

function WorkflowLayer() {
  return (
    <section className="landing-layer landing-workflow-layer">
      <div className="landing-layer-head">
        <span>
          <BranchesOutlined /> Workflow Canvas
        </span>
        <strong>running</strong>
      </div>
      <div className="landing-node-row">
        {workflowNodes.map(([type, title], index) => (
          <div className="landing-node" key={title}>
            <span>{type}</span>
            <strong>{title}</strong>
            {index < workflowNodes.length - 1 && <i aria-hidden="true" />}
          </div>
        ))}
      </div>
    </section>
  );
}

function ArtifactLayer() {
  return (
    <section className="landing-layer landing-artifact-layer">
      <div className="landing-layer-head">
        <span>
          <FileTextOutlined /> Artifact Preview
        </span>
        <strong>PDF</strong>
      </div>
      <div className="landing-document-page">
        <h3>AgentHub 项目发布方案</h3>
        <p>多智能体协作平台 · 正式文档预览</p>
        <ul>
          <li>
            <CheckCircleOutlined /> 结构化 DocumentModel 渲染
          </li>
          <li>
            <FunctionOutlined /> artifact.create_pdf 真实产物
          </li>
          <li>
            <AuditOutlined /> ToolInvocation 审计记录
          </li>
          <li>
            <ApiOutlined /> Tool / Skill / MCP 统一能力目录
          </li>
        </ul>
      </div>
    </section>
  );
}

function ToolRunLayer() {
  return (
    <section className="landing-layer landing-tool-layer">
      <div>
        <span>
          <ThunderboltOutlined /> 调用：artifact.create_pdf
        </span>
        <strong>succeeded · 842ms</strong>
      </div>
      <div>
        <span>
          <CodeOutlined /> sandbox.run
        </span>
        <strong>exit_code 0</strong>
      </div>
      <div>
        <span>
          <MessageOutlined /> message_stop
        </span>
        <strong>completed</strong>
      </div>
    </section>
  );
}
