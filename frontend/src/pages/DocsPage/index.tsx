import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  MenuFoldOutlined,
  SearchOutlined,
  UsergroupAddOutlined,
} from "@ant-design/icons";
import {
  apiSections,
  capabilitySections,
  maintainCards,
  navGroups,
  quickEntries,
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

function DocsAnnouncement({ onClose }: { onClose: () => void }) {
  return (
    <div className="docs-announcement">
      <span>
        AgentHub 文档站已扩展为详细指南，覆盖快速开始、API、模型运行、工具接入和排查入口。
      </span>
      <a href="#updates">查看详情 →</a>
      <button
        type="button"
        aria-label="关闭公告"
        onClick={onClose}
      >
        ×
      </button>
    </div>
  );
}

function DocsTopbar() {
  return (
    <header className="docs-topbar">
      <a className="docs-brand" href="#welcome" aria-label="AgentHub 文档首页">
        <span className="docs-brand-mark">A</span>
        <span>AgentHub</span>
      </a>
      <a className="docs-invite" href="#workspace">
        <UsergroupAddOutlined />
        <span>协作空间</span>
      </a>
      <nav className="docs-nav" aria-label="文档导航">
        <a href="#contact">联系我们</a>
        <a href="#welcome">文档</a>
        <a href="#api-overview">API</a>
        <a className="docs-token" href="#first-run">
          Demo Plan ↗
        </a>
        <Link to="/app">控制台</Link>
        <a href="#updates">博客</a>
        <span>中文 ▾</span>
        <span className="docs-user-dot" aria-hidden="true">
          <UsergroupAddOutlined />
        </span>
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
        <a id="contact" href="#faq">
          开发者交流群
        </a>
        <a href="#first-run">
          免费体验 AgentHub <strong>HOT</strong>
        </a>
      </div>
    </aside>
  );
}

function DocsHero() {
  return (
    <section id="welcome" className="docs-hero-section">
      <h1>AgentHub 多 Agent 协作平台说明文档</h1>
      <div className="docs-visual-hero">
        <div className="docs-line-field" />
        <div className="docs-pulse-grid" />
        <div className="docs-hero-logo">AgentHub</div>
        <div className="docs-hero-copy">
          <h2>AgentHub Docs 正式上线</h2>
          <p>
            从首次登录、模型运行、API 接入到工具/Skill/MCP 扩展，按真实使用链路组织说明，让开发和演示都能顺着文档走完闭环。
          </p>
        </div>
        <Link className="docs-hero-action" to="/app">
          进入控制台 →
        </Link>
        <div className="docs-hero-dots" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
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
          <a className="docs-entry-card" href="#first-run" key={entry.title}>
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

function DemoFlowSection() {
  return (
    <section id="demo-flow" className="docs-section docs-two-column">
      <div>
        <h2>演示链路</h2>
        <p>
          推荐从演示用户进入系统，创建一个工作区，再发起单聊或多 Agent 群聊。单聊会使用当前
          Agent 的工具权限执行，群聊会优先读取画布 workflow。
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
    <section id="workspace" className="docs-section">
      <h2>核心能力</h2>
      <div className="docs-capability-grid">
        {capabilitySections.map((item) => (
          <article className="docs-capability" id={item.id} key={item.id}>
            <span>{item.icon}</span>
            <h3>{item.title}</h3>
            <p>{item.description}</p>
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

export function DocsPage() {
  const [query, setQuery] = useState("");
  const [announcementVisible, setAnnouncementVisible] = useState(true);
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
    <main
      className={`docs-shell ${
        announcementVisible ? "docs-shell-announced" : "docs-shell-plain"
      }`}
    >
      {announcementVisible ? (
        <DocsAnnouncement onClose={() => setAnnouncementVisible(false)} />
      ) : null}
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
            <a href="#first-run">首次运行会话 ›</a>
          </section>
        </section>
      </div>
    </main>
  );
}
