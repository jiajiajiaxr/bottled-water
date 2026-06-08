import { Link } from "react-router-dom";
import {
  ApiOutlined,
  ArrowRightOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  GithubOutlined,
  PlayCircleOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";

const launchStats = [
  { value: "36", label: "function tools exposed" },
  { value: "4", label: "agent roles in one run" },
  { value: "1", label: "workspace memory boundary" },
  { value: "2026.06", label: "release build" },
];

const releaseHighlights = [
  {
    icon: <DeploymentUnitOutlined />,
    title: "自动组织多 Agent 干活",
    text: "Team Leader 会拆任务、调度角色、收集 work product，并把公开结果写入消息流和 Blackboard。",
  },
  {
    icon: <CodeOutlined />,
    title: "真实外部 Coding Agent",
    text: "Codex、Claude Code、OpenCode 走 external_agent.invoke，记录 stdout、stderr、退出码和 changed files。",
  },
  {
    icon: <BranchesOutlined />,
    title: "工作流从演示变成运行态",
    text: "AI 生成工作流、节点试运行、右侧运行记录和历史版本围绕同一套上下文打通。",
  },
  {
    icon: <CloudServerOutlined />,
    title: "Docker 部署文档更新",
    text: "一键部署说明、容器健康检查、环境变量和回滚边界按当前版本重新整理。",
  },
];

const runSteps = [
  {
    label: "Plan",
    title: "识别目标与约束",
    text: "从用户消息、文件、长期记忆和工作区状态里拼出任务上下文。",
  },
  {
    label: "Assign",
    title: "分配给合适 Agent",
    text: "按产品、前端、后端、部署、评审等角色拆分责任与依赖。",
  },
  {
    label: "Execute",
    title: "调用真实工具",
    text: "运行 MCP、内置工具、外部 Coding Agent、沙箱命令或产物生成器。",
  },
  {
    label: "Verify",
    title: "沉淀可追踪结果",
    text: "把产物、工具结果、Blackboard、消息和 generation 记录串起来。",
  },
];

const capabilityBlocks = [
  {
    icon: <FileSearchOutlined />,
    title: "上下文与记忆",
    points: ["当前会话短期历史", "群聊发言身份", "Blackboard 共享上下文", "Workspace 长期记忆"],
  },
  {
    icon: <ExperimentOutlined />,
    title: "真实工具执行",
    points: ["sandbox.run", "test.run", "external_agent.invoke", "artifact.update / diff"],
  },
  {
    icon: <SafetyCertificateOutlined />,
    title: "协作边界",
    points: ["公开结果可见", "私有 Agent Context 隔离", "跨会话不默认读取", "工具结果作为事实源"],
  },
];

const releaseChecklist = [
  "AI 工作流生成与右侧试运行修复",
  "Daily Agent 默认工具上下文补全",
  "Claude Code / Codex 外部 Agent 记录链路",
  "Docker 部署文档与健康检查说明更新",
  "登录页视觉升级，桌面和移动端适配",
  "群聊协作进度、结果汇总和公开记忆边界",
];

const demoRoutes = [
  "让 Daily Chat Agent 调 Claude Code 计算 5 + 9",
  "组织 4 个 Agent 生成 MVP 方案并完成评审",
  "AI 生成一个工作流，在右侧逐节点试运行",
  "创建 HTML 产物，预览、保存版本、Diff、部署",
];

function ProductReleaseNav() {
  return (
    <header className="release-nav">
      <Link className="release-brand" to="/release" aria-label="AgentHub release home">
        <span className="release-brand-mark">A</span>
        <span>AgentHub</span>
      </Link>
      <nav aria-label="Product release navigation">
        <a href="#capabilities">能力</a>
        <a href="#workflow">运行链路</a>
        <a href="#checklist">发布清单</a>
        <Link to="/docs">文档</Link>
      </nav>
      <Link className="release-nav-cta" to="/app">
        打开控制台
        <ArrowRightOutlined />
      </Link>
    </header>
  );
}

function ProductReleaseHero() {
  return (
    <section className="release-hero" aria-labelledby="release-hero-title">
      <img
        className="release-hero-image"
        src="/agenthub-release-workbench.png"
        alt="AgentHub 多智能体工作台运行截图"
      />
      <div className="release-hero-shade" />
      <ProductReleaseNav />
      <div className="release-hero-content">
        <div className="release-kicker">
          <RocketOutlined />
          2026 Release
        </div>
        <h1 id="release-hero-title">
          AgentHub AI
          <span>协作工作台</span>
        </h1>
        <p>
          面向真实交付的多智能体平台：能组织 Agent 接力干活，调用 Claude Code / Codex，
          运行工作流、沉淀产物，并把每次执行变成可追踪的发布事实。
        </p>
        <div className="release-hero-actions">
          <Link className="release-primary-button" to="/app">
            <PlayCircleOutlined />
            进入产品
          </Link>
          <Link className="release-secondary-button" to="/docs">
            查看文档
            <ArrowRightOutlined />
          </Link>
        </div>
      </div>
      <div className="release-signal-strip" aria-label="Launch metrics">
        {launchStats.map((item) => (
          <div key={item.label}>
            <strong>{item.value}</strong>
            <span>{item.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function ProductReleasePage() {
  return (
    <main className="release-page">
      <ProductReleaseHero />

      <section id="capabilities" className="release-section release-intro-section">
        <div className="release-section-heading">
          <span>Why this release</span>
          <h2>从“AI 回复”推进到“AI 真实执行”</h2>
          <p>
            这版发布页围绕你现在最关心的能力展开：不是看起来像完成了，而是工具真实调用、
            文件真实变化、运行结果真实可查。
          </p>
        </div>
        <div className="release-highlight-grid">
          {releaseHighlights.map((item) => (
            <article className="release-highlight" key={item.title}>
              <div className="release-icon">{item.icon}</div>
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="workflow" className="release-section release-flow-section">
        <div className="release-section-heading release-section-heading-left">
          <span>Operating model</span>
          <h2>一次任务如何被组织、执行、验证</h2>
        </div>
        <div className="release-flow">
          {runSteps.map((step, index) => (
            <article className="release-flow-step" key={step.label}>
              <div className="release-step-index">{String(index + 1).padStart(2, "0")}</div>
              <span>{step.label}</span>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="release-section release-command-section">
        <div className="release-command-copy">
          <span>Real agent invocation</span>
          <h2>外部 Coding Agent 已进入产品能力边界</h2>
          <p>
            Claude Code、Codex 和 OpenCode 统一走 external_agent.invoke。
            平台不只展示“完成了”，还会保存运行 ID、工作目录、输出摘要、错误、耗时和变更文件。
          </p>
        </div>
        <div className="release-terminal" aria-label="External agent run example">
          <div className="release-terminal-bar">
            <span />
            <span />
            <span />
          </div>
          <pre>{`tool: external_agent.invoke
provider: claude_code
action: run
task: 调用 Claude Code 算一下 5+9

status: completed
stdout_tail: 5 + 9 = 14
exit_code: 0
changed_files: []`}</pre>
        </div>
      </section>

      <section className="release-section release-capability-section">
        <div className="release-capability-grid">
          {capabilityBlocks.map((block) => (
            <article className="release-capability" key={block.title}>
              <div className="release-icon">{block.icon}</div>
              <h3>{block.title}</h3>
              <ul>
                {block.points.map((point) => (
                  <li key={point}>
                    <CheckCircleOutlined />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section id="checklist" className="release-section release-list-section">
        <div className="release-list-panel">
          <div className="release-section-heading release-section-heading-left">
            <span>Release notes</span>
            <h2>这一版已经准备好的发布点</h2>
          </div>
          <ul className="release-checklist">
            {releaseChecklist.map((item) => (
              <li key={item}>
                <CheckCircleOutlined />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="release-list-panel release-demo-panel">
          <div className="release-section-heading release-section-heading-left">
            <span>Demo path</span>
            <h2>建议演示路线</h2>
          </div>
          <ol className="release-demo-list">
            {demoRoutes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </div>
      </section>

      <section className="release-section release-final-cta">
        <ThunderboltOutlined />
        <h2>把 AgentHub 当成真实工作台，而不是聊天样板间</h2>
        <p>
          现在可以围绕“自动组织、多 Agent 协作、真实工具调用、产物发布”做一条完整产品演示线。
        </p>
        <div>
          <Link className="release-primary-button" to="/app">
            打开控制台
            <ArrowRightOutlined />
          </Link>
          <Link className="release-secondary-button" to="/docs">
            <GithubOutlined />
            发布文档
          </Link>
        </div>
      </section>
    </main>
  );
}
