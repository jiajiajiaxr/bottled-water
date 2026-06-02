import {
  BookOutlined,
  GithubOutlined,
  PlayCircleOutlined,
  RocketOutlined,
} from "@ant-design/icons";
import { Button } from "antd";
import { Link } from "react-router-dom";

import { ProductShowcase } from "./ProductShowcase";
import {
  ArchitectureSection,
  CapabilitySection,
  DeveloperSection,
  FinalCtaSection,
  MetricsSection,
  ProductLoopSection,
  ScenarioSection,
} from "./Sections";
import { githubUrl } from "./content";
import "./landing.css";

export function LandingPage() {
  return (
    <main className="landing-shell">
      <LandingNav />
      <section className="landing-hero">
        <div className="landing-hero-copy">
          <span className="landing-eyebrow">Multi-Agent Collaboration Platform</span>
          <h1>AgentHub 多智能体协作工作台</h1>
          <p>
            用 IM 群聊组织 Agent，用工作流画布编排任务，用 Tool / Skill / MCP
            生成真实产物。
          </p>
          <div className="landing-cta-row">
            <Button type="primary" size="large" icon={<PlayCircleOutlined />}>
              <Link to="/app">进入演示</Link>
            </Button>
            <Button size="large" icon={<GithubOutlined />} href={githubUrl}>
              查看 GitHub
            </Button>
            <Button size="large" icon={<BookOutlined />}>
              <Link to="/docs">阅读文档</Link>
            </Button>
          </div>
          <div className="landing-hero-proof">
            <span>真实 Function Call</span>
            <span>会话级工作流</span>
            <span>沙箱与审计</span>
          </div>
        </div>
        <ProductShowcase />
      </section>
      <MetricsSection />
      <CapabilitySection />
      <ProductLoopSection />
      <ArchitectureSection />
      <DeveloperSection />
      <ScenarioSection />
      <FinalCtaSection />
    </main>
  );
}

function LandingNav() {
  return (
    <header className="landing-nav">
      <Link className="landing-brand" to="/landing" aria-label="AgentHub 发布页">
        <span>AH</span>
        <strong>AgentHub</strong>
      </Link>
      <nav aria-label="发布页导航">
        <a href="#capabilities">产品能力</a>
        <a href="#architecture">架构</a>
        <a href="#demo-flow">演示流程</a>
        <Link to="/docs">文档</Link>
        <a href={githubUrl}>GitHub</a>
      </nav>
      <Button type="primary" icon={<RocketOutlined />}>
        <Link to="/app">进入演示</Link>
      </Button>
    </header>
  );
}

