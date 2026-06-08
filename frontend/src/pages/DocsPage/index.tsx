import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiOutlined,
  BranchesOutlined,
  BulbOutlined,
  CodeOutlined,
  HomeOutlined,
  MenuFoldOutlined,
  RocketOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  apiSections,
  capabilitySections,
  maintainCards,
  navGroups,
  quickEntries,
  readingPaths,
  localBootCode,
} from "./content";
import type { NavGroup } from "./content";
import {
  AssetLifecycleSection,
  ApiDetailsSection,
  CapabilityMapSection,
  CodePanel,
  FirstRunGuide,
  IntegrationSection,
  ModelRuntimeSection,
  ProductPlatformSection,
  TroubleshootingSection,
  UpdatesSection,
  WorkflowNodeSection,
} from "./DetailSections";
import "./docs.css";
import "./docs-detail.css";
import "./docs-hero.css";
import "./docs-responsive.css";

function DocsTopbar() {
  return (
    <header className="docs-topbar">
      <a className="docs-brand" href="#welcome" aria-label="AgentHub 文档首页">
        <span className="docs-brand-mark">A</span>
        <span>AgentHub</span>
      </a>
      <nav className="docs-nav" aria-label="文档导航">
        <a href="#start">快速开始</a>
        <a href="#capability-map">核心概念</a>
        <a href="#workflow-nodes">工作流</a>
        <a href="#api-overview">API</a>
        <a href="#integration">扩展</a>
        <a href="#faq">排查</a>
        <Link className="docs-console-link" to="/app">
          打开控制台
        </Link>
      </nav>
    </header>
  );
}

function DocsSidebar({
  groups,
  query,
  onQueryChange,
}: {
  groups: NavGroup[];
  query: string;
  onQueryChange: (value: string) => void;
}) {
  return (
    <aside className="docs-sidebar" aria-label="文档目录">
      <button className="docs-menu-button" type="button" aria-label="折叠菜单">
        <MenuFoldOutlined />
      </button>
      <label className="docs-search">
        <SearchOutlined />
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="搜索文档"
          aria-label="搜索文档"
        />
      </label>
      <a className="docs-sidebar-home" href="#welcome">
        欢迎使用
      </a>
      {groups.map((group) => (
        <section className="docs-nav-group" key={group.title}>
          <h2>{group.title}</h2>
          {group.links.map((link) => (
            <a key={link.href} href={link.href}>
              {link.title}
            </a>
          ))}
        </section>
      ))}
      <div className="docs-sidebar-foot">
        <a href="#api-overview">
          API 与 SDK
        </a>
        <a href="#faq">
          排查入口 <strong>NEW</strong>
        </a>
      </div>
    </aside>
  );
}

function DocsHero() {
  return (
    <section id="welcome" className="docs-hero-section">
      <div className="docs-hero-label">
        <BulbOutlined aria-hidden="true" />
        AgentHub Docs
      </div>
      <h1>AgentHub 多 Agent 协作平台文档</h1>
      <p className="docs-hero-lead">
        从第一次会话、模型配置、工作流编排到 API 接入和工具扩展，这里按真实任务路径组织说明，帮助团队更快把 AgentHub 用起来、接起来、维护好。
      </p>
      <div className="docs-visual-hero">
        <div className="docs-line-field" />
        <div className="docs-pulse-grid" />
        <div className="docs-hero-logo">Docs</div>
        <div className="docs-hero-copy">
          <h2>从使用路径开始，而不是从概念堆栈开始</h2>
          <p>
            先跑通最小闭环，再理解工作区、Agent、工具、工作流和产物生命周期；需要集成时直接跳到 API、SDK 和扩展章节。
          </p>
        </div>
        <Link className="docs-hero-action" to="/app">
          打开控制台
        </Link>
      </div>
    </section>
  );
}

function QuickStartSection() {
  return (
    <section id="start" className="docs-section">
      <h2>快速开始</h2>
      <div className="docs-quick-grid">
        {quickEntries.map((entry) => (
          <a className="docs-entry-card" href={entry.href} key={entry.title}>
            <span className="docs-entry-icon">{entry.icon}</span>
            <span>
              <strong>{entry.title}</strong>
              <small>{entry.description}</small>
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}

function ReadingPathSection() {
  return (
    <section id="reading-path" className="docs-section docs-reading-path">
      <div className="docs-section-head">
        <RocketOutlined />
        <div>
          <h2>选择你的阅读路径</h2>
          <p>
            好的文档会先帮用户判断该读什么。这里按常见角色给出最短路径，避免从长目录里猜入口。
          </p>
        </div>
      </div>
      <div className="docs-path-grid">
        {readingPaths.map((path) => (
          <a className="docs-path-card" href={path.href} key={path.title}>
            <span>{path.audience}</span>
            <strong>{path.title}</strong>
            <p>{path.description}</p>
            <ol>
              {path.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </a>
        ))}
      </div>
    </section>
  );
}

function DemoFlowSection() {
  return (
    <section id="demo-flow" className="docs-section docs-two-column">
      <div>
        <h2>演示链路</h2>
        <p>
          推荐先从演示用户进入控制台，创建或选择一个工作区，再发起单聊或多 Agent 群聊。单聊会使用当前
          Agent 的工具权限执行，群聊会优先读取画布 workflow，让演示过程可复盘、可定位。
        </p>
        <div className="docs-steps">
          <span>登录</span>
          <span>选择工作区</span>
          <span>配置 Agent</span>
          <span>运行会话</span>
          <span>预览产物</span>
        </div>
      </div>
      <div id="local">
        <CodePanel title="本地启动" code={localBootCode} />
      </div>
    </section>
  );
}

function CapabilitySection() {
  return (
    <section id="workspace" className="docs-section docs-capability-deep">
      <div className="docs-capability-intro">
        <span className="docs-capability-kicker">Core model</span>
        <h2>核心能力不是功能清单，而是一条从输入到交付的链路</h2>
        <p>
          AgentHub 的核心能力可以按四层理解：会话负责承接任务，Agent 负责角色化执行，workflow 负责稳定编排，文件与产物负责把上下文和交付物沉淀下来。
          这四层需要一起看，单独看某一个按钮或模块，很容易把平台误解成普通聊天界面。
        </p>
        <div className="docs-capability-tabs" aria-label="核心能力快捷入口">
          {capabilitySections.map((item) => (
            <a href={`#${item.id}`} key={item.id}>
              {item.icon}
              {item.title}
            </a>
          ))}
        </div>
      </div>
      <div className="docs-capability-story">
        {capabilitySections.map((item, index) => (
          <article className="docs-capability-row" id={item.id} key={item.id}>
            <div className="docs-capability-index">
              <span>{String(index + 1).padStart(2, "0")}</span>
              {item.icon}
            </div>
            <div className="docs-capability-body">
              <h3>{item.title}</h3>
              <p>{item.description}</p>
              {item.scenario ? (
                <div className="docs-capability-scenario">
                  <strong>适用场景</strong>
                  <p>{item.scenario}</p>
                </div>
              ) : null}
            </div>
            <div className="docs-capability-operate">
              <strong>操作路径</strong>
              <ol>
                {item.steps?.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </div>
            <div className="docs-capability-signals">
              <strong>观察点</strong>
              <ul>
                {item.signals?.map((signal) => (
                  <li key={signal}>{signal}</li>
                ))}
              </ul>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ApiSection() {
  return (
    <section className="docs-section docs-api-band">
      <div>
        <h2>API 文档</h2>
        <p>
          后端以 FastAPI 提供认证、会话、消息、Agent、工具、文件、产物、部署、审计等接口，前端通过统一
          API SDK 调用。
        </p>
        <div className="docs-api-actions">
          <a href="#api-overview">
            <ApiOutlined />
            查看接口总览
          </a>
          <a href="#frontend-sdk">
            <CodeOutlined />
            前端 SDK 示例
          </a>
        </div>
      </div>
      <div className="docs-api-list">
        {apiSections.map((item) => (
          <a id={item.id} href="#api-overview" key={item.id}>
            <span>{item.icon}</span>
            <strong>{item.title}</strong>
            <small>{item.meta}</small>
          </a>
        ))}
      </div>
    </section>
  );
}

function MaintainSection() {
  return (
    <section id="security" className="docs-section docs-maintain-grid">
      {maintainCards.map((item) => (
        <article id={item.id} key={item.title}>
          {item.icon}
          <h3>{item.title}</h3>
          <p>{item.description}</p>
        </article>
      ))}
    </section>
  );
}

function DocsUtilityRail() {
  return (
    <aside className="docs-utility-rail" aria-label="文档辅助入口">
      <a href="#welcome">
        <HomeOutlined />
        顶部
      </a>
      <a href="#api-overview">
        <ApiOutlined />
        API
      </a>
      <a href="#workflow-nodes">
        <BranchesOutlined />
        工作流
      </a>
      <a href="#faq">
        <SearchOutlined />
        排查
      </a>
    </aside>
  );
}

export function DocsPage() {
  const [query, setQuery] = useState("");
  const filteredGroups = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return navGroups;

    return navGroups
      .map((group) => ({
        ...group,
        links: group.links.filter((link) =>
          `${group.title} ${link.title}`.toLowerCase().includes(normalized),
        ),
      }))
      .filter((group) => group.links.length > 0);
  }, [query]);

  return (
    <main className="docs-shell">
      <DocsTopbar />
      <div className="docs-layout">
        <DocsSidebar
          groups={filteredGroups}
          query={query}
          onQueryChange={setQuery}
        />
        <section className="docs-content">
          <div className="docs-breadcrumb">文档 &gt; 欢迎使用</div>
          <DocsHero />
          <QuickStartSection />
          <ReadingPathSection />
          <ProductPlatformSection />
          <DemoFlowSection />
          <FirstRunGuide />
          <CapabilitySection />
          <CapabilityMapSection />
          <ModelRuntimeSection />
          <WorkflowNodeSection />
          <ApiSection />
          <ApiDetailsSection />
          <IntegrationSection />
          <AssetLifecycleSection />
          <MaintainSection />
          <TroubleshootingSection />
          <UpdatesSection />
          <section className="docs-next">
            <span>下一篇</span>
            <a href="#first-run">首次运行会话</a>
          </section>
        </section>
        <DocsUtilityRail />
      </div>
    </main>
  );
}
