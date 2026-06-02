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
  capabilities,
  githubUrl,
  metrics,
  productFlow,
  scenarios,
  stackItems,
  workflowCode,
} from "./content";

const capabilityIcons = [
  BranchesOutlined,
  FunctionOutlined,
  DeploymentUnitOutlined,
  ApiOutlined,
  FileDoneOutlined,
  SafetyCertificateOutlined,
];

export function MetricsSection() {
  return (
    <section className="landing-metric-band" aria-label="AgentHub 产品指标">
      {metrics.map((metric) => (
        <article key={metric.label}>
          <strong>{metric.value}</strong>
          <span>{metric.label}</span>
        </article>
      ))}
    </section>
  );
}

export function CapabilitySection() {
  return (
    <section id="capabilities" className="landing-section">
      <SectionHeader
        eyebrow="Product Loop"
        title="围绕“可见结果”组织产品能力"
        body="每个模块都不是孤立功能，而是回答两个问题：它解决什么协作痛点，演示时用户能看到什么真实结果。"
      />
      <div className="landing-capability-grid">
        {capabilities.map((item, index) => {
          const Icon = capabilityIcons[index] ?? FunctionOutlined;
          return (
            <article className="landing-capability-card" key={item.title}>
              <div className="landing-card-head">
                <span className="landing-card-icon">
                  <Icon />
                </span>
                <span>{item.eyebrow}</span>
              </div>
              <h3>{item.title}</h3>
              <dl>
                <dt>解决什么问题</dt>
                <dd>{item.problem}</dd>
                <dt>演示时能看到</dt>
                <dd>{item.demo}</dd>
              </dl>
              <div className="landing-tag-row">
                {item.signals.map((signal) => (
                  <Tag key={signal}>{signal}</Tag>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

export function ProductLoopSection() {
  return (
    <section id="demo-flow" className="landing-section landing-loop-section">
      <SectionHeader
        eyebrow="Demo Flow"
        title="从一句需求到真实产物的闭环"
        body="发布页和答辩演示可以沿着这条链路展开：上下文如何进入、Agent 如何协作、工具如何执行、产物如何落地。"
      />
      <div className="landing-loop">
        {productFlow.map((step, index) => (
          <article className="landing-loop-step" key={step.title}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{step.title}</strong>
            <p>{step.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ArchitectureSection() {
  return (
    <section id="architecture" className="landing-section">
      <SectionHeader
        eyebrow="Architecture"
        title="为多 Agent Function Call 工作流准备的分层架构"
        body="聊天编排、工作流、Agent Loop、工具执行、文件产物和实时事件互相解耦，方便后续继续扩展。"
      />
      <div className="landing-architecture-map">
        <div className="landing-architecture-core">
          <strong>AgentHub Core</strong>
          <span>Conversation · Workflow · Context</span>
        </div>
        {architectureModules.map(([title, body]) => (
          <article key={title}>
            <h3>{title}</h3>
            <p>{body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function DeveloperSection() {
  return (
    <section id="developers" className="landing-section landing-developer-section">
      <div>
        <SectionHeader
          eyebrow="Developer Ready"
          title="技术栈清晰，方便展示也方便接着做"
          body="前端 React + Ant Design，后端 FastAPI + SQLAlchemy，数据库、沙箱、文件和工具目录都有明确边界。"
        />
        <div className="landing-stack">
          {stackItems.map((item) => (
            <Tag key={item}>{item}</Tag>
          ))}
        </div>
      </div>
      <div className="landing-code-panel">
        <div className="landing-code-head">
          <span>
            <CodeOutlined /> conversation.workflow
          </span>
          <Tag color="cyan">Function Call</Tag>
        </div>
        <pre>
          <code>{workflowCode}</code>
        </pre>
      </div>
    </section>
  );
}

export function ScenarioSection() {
  return (
    <section id="scenarios" className="landing-section">
      <SectionHeader
        eyebrow="Demo Scenarios"
        title="五条真实演示路径"
        body="这些场景能快速证明平台不是壳：每条路径都有真实工具调用、状态记录和可见产物。"
      />
      <div className="landing-scenario-grid">
        {scenarios.map((scenario) => (
          <article className="landing-scenario-card" key={scenario.title}>
            <CheckCircleOutlined />
            <h3>{scenario.title}</h3>
            <p className="landing-scenario-prompt">{scenario.prompt}</p>
            <p>{scenario.result}</p>
            <Tag>{scenario.tool}</Tag>
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
        <span className="landing-eyebrow">Ship the platform</span>
        <h2>把 AgentHub 作为完整平台展示，而不是一组分散 Demo。</h2>
      </div>
      <div className="landing-cta-row">
        <Button type="primary" size="large" icon={<DeploymentUnitOutlined />}>
          <Link to="/app">进入 AgentHub</Link>
        </Button>
        <Button size="large" icon={<CloudServerOutlined />} href={githubUrl}>
          查看 GitHub
        </Button>
        <Button size="large" icon={<DatabaseOutlined />}>
          <Link to="/docs">阅读文档</Link>
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

