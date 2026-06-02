import {
  ApiOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FileDoneOutlined,
  FunctionOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Button, Tag } from "antd";
import { Link } from "react-router-dom";

import {
  architectureModules,
  capabilityCards,
  codeExample,
  githubUrl,
  metrics,
  productFlow,
  scenarioCards,
} from "./content";

const stackItems = [
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

const capabilityIcons = [
  BranchesOutlined,
  FunctionOutlined,
  ApiOutlined,
  DeploymentUnitOutlined,
  FileDoneOutlined,
  SafetyCertificateOutlined,
];

export function CapabilitySection() {
  return (
    <section id="capabilities" className="landing-section">
      <SectionHeader
        eyebrow="Product Surface"
        title="把 Agent 协作、工具执行和产物交付放进同一个工作台"
        body="AgentHub 不是只聊天，也不是只画流程。它把会话、工作流、工具、文件和审计连接成一条可演示、可恢复的闭环。"
      />
      <div className="landing-capability-grid">
        {capabilityCards.map((card, index) => {
          const Icon = capabilityIcons[index] ?? FunctionOutlined;
          return (
            <article className="landing-capability-card" key={card.title}>
              <span className="landing-card-icon">
                <Icon />
              </span>
              <span className="landing-card-kicker">{card.kicker}</span>
              <h3>{card.title}</h3>
              <p>{card.body}</p>
              <div className="landing-mini-tags">
                {card.points.map((point) => (
                  <Tag key={point}>{point}</Tag>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function MetricsSection() {
  return (
    <section className="landing-metrics" aria-label="AgentHub 指标">
      {metrics.map((metric) => (
        <div key={metric.label}>
          <strong>{metric.value}</strong>
          <span>{metric.label}</span>
        </div>
      ))}
    </section>
  );
}

export function ProductLoopSection() {
  return (
    <section id="demo-flow" className="landing-section">
      <SectionHeader
        eyebrow="Demo Flow"
        title="从一句需求到真实产物的协作闭环"
        body="演示时可以沿着这条链路讲清楚：Agent 如何分工、工具如何执行、产物如何预览，最终如何审查和交付。"
      />
      <div className="landing-loop">
        {productFlow.map((step, index) => (
          <article className="landing-loop-step" key={step}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{step}</strong>
            {index < productFlow.length - 1 && <i aria-hidden="true" />}
          </article>
        ))}
      </div>
    </section>
  );
}

export function ArchitectureSection() {
  return (
    <section id="architecture" className="landing-section landing-architecture">
      <SectionHeader
        eyebrow="Architecture"
        title="面向多 Agent Function Call 工作流的模块化后端"
        body="依赖方向清晰：chat 调 workflow / agents，agents 调 llm / tools，tools 再分发 builtin、Skill 和 MCP。"
      />
      <div className="landing-architecture-grid">
        {architectureModules.map((module, index) => (
          <article className="landing-architecture-card" key={module.title}>
            <span>{index + 1}</span>
            <h3>{module.title}</h3>
            <p>{module.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function DeveloperSection() {
  return (
    <section id="developers" className="landing-section landing-developers">
      <div>
        <SectionHeader
          eyebrow="Developer Ready"
          title="工程栈清晰，适合二次开发和答辩追问"
          body="前后端分离、数据库目录化、沙箱与文件系统按工作区隔离，核心能力都有测试覆盖。"
        />
        <div className="landing-stack-grid">
          {stackItems.map((item) => (
            <Tag key={item}>{item}</Tag>
          ))}
        </div>
      </div>
      <div className="landing-code-panel">
        <div className="landing-code-head">
          <span>
            <CodeOutlined /> workflow-node.json
          </span>
          <Tag color="cyan">Function Call</Tag>
        </div>
        <pre>
          <code>{codeExample}</code>
        </pre>
      </div>
    </section>
  );
}

export function ScenarioSection() {
  return (
    <section id="scenarios" className="landing-section">
      <SectionHeader
        eyebrow="Demo Scripts"
        title="五条稳定演示路径"
        body="每个场景都能展示一个真实闭环：聊天输入、Agent 决策、工具执行、运行态和产物交付。"
      />
      <div className="landing-scenario-grid">
        {scenarioCards.map((scenario) => (
          <article className="landing-scenario-card" key={scenario}>
            <CheckCircleOutlined />
            <h3>{scenario}</h3>
            <p>可在单聊、群聊或工作流画布里演示，并保留审计记录。</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function FinalCtaSection() {
  return (
    <section className="landing-final-cta">
      <div>
        <span className="landing-eyebrow">Ship the demo</span>
        <h2>把 AgentHub 作为一个完整平台展示，而不是一组分散 Demo。</h2>
      </div>
      <div className="landing-cta-row">
        <Button type="primary" size="large" icon={<DeploymentUnitOutlined />}>
          <Link to="/app">进入 AgentHub</Link>
        </Button>
        <Button size="large" icon={<CloudServerOutlined />} href={githubUrl}>
          查看 GitHub
        </Button>
        <Button size="large" icon={<DatabaseOutlined />}>
          <Link to="/docs">阅读 README</Link>
        </Button>
      </div>
    </section>
  );
}

function SectionHeader({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div className="landing-section-head">
      <span className="landing-eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  );
}

