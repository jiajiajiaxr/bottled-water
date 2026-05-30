import {
  ApiOutlined,
  BranchesOutlined,
  CloudServerOutlined,
  CodeOutlined,
  DatabaseOutlined,
  FileProtectOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import {
  apiExampleCode,
  endpointEntries,
  integrationSteps,
  runtimeEntries,
  troubleshootingRows,
  updateItems,
  workflowExampleCode,
} from "./content";
import {
  assetLifecycleEntries,
  capabilityRows,
  journeyEntries,
  productModules,
  workflowNodeDocs,
} from "./platformContent";

export function CodePanel({ title, code }: { title: string; code: string }) {
  return (
    <div className="docs-code-panel">
      <div className="docs-code-title">
        <CloudServerOutlined />
        {title}
      </div>
      <pre>{code}</pre>
    </div>
  );
}

export function ProductPlatformSection() {
  return (
    <section id="platform-overview" className="docs-section docs-platform-band">
      <div className="docs-section-head">
        <DatabaseOutlined />
        <div>
          <h2>产品平台总览</h2>
          <p>
            AgentHub 是围绕 IM 协作组织的多 Agent 工作台。平台把会话、工作区、Agent 能力、工作流、文件产物和安全治理放在同一套产品链路里，适合演示从需求输入到交付预览的完整过程。
          </p>
        </div>
      </div>
      <div className="docs-platform-grid">
        {productModules.map((module) => (
          <article className="docs-platform-card" key={module.title}>
            <span className="docs-platform-icon">{module.icon}</span>
            <h3>{module.title}</h3>
            <p>{module.description}</p>
            <ul>
              {module.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
      <div id="personas" className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>角色</th>
              <th>入口</th>
              <th>推荐路径</th>
              <th>完成结果</th>
            </tr>
          </thead>
          <tbody>
            {journeyEntries.map((entry) => (
              <tr key={entry.role}>
                <td>{entry.role}</td>
                <td>{entry.entry}</td>
                <td>{entry.path}</td>
                <td>{entry.outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function FirstRunGuide() {
  return (
    <section id="first-run" className="docs-section docs-guide-band">
      <div>
        <h2>首次运行会话</h2>
        <p>
          AgentHub 的最小闭环是：登录、选择工作区、创建会话、选择 Agent、发送消息、查看流式回复和可选产物。
          单聊直接运行当前 Agent 的小循环；群聊会优先读取会话内保存的 workflow。
        </p>
        <ol className="docs-numbered-list">
          <li>使用演示用户进入控制台，确认左上角工作区已选中。</li>
          <li>新建单聊时选择一个官方 Agent，例如 Reviewer 或 Frontend Worker。</li>
          <li>上传文件或输入需求，发送后观察消息流、工具摘要和后台任务。</li>
          <li>如果出现产物卡片，点击后在右侧预览、编辑、Diff 或导出。</li>
        </ol>
      </div>
      <CodePanel title="前端 SDK 调用示例" code={apiExampleCode} />
    </section>
  );
}

export function CapabilityMapSection() {
  return (
    <section id="capability-map" className="docs-section docs-capability-map">
      <div className="docs-section-head">
        <ToolOutlined />
        <div>
          <h2>平台能力地图</h2>
          <p>
            下表按产品控制台入口梳理能力边界。排查问题时先定位用户正在使用的控制台区域，再顺着后端 API 和服务层查运行记录。
          </p>
        </div>
      </div>
      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>能力域</th>
              <th>控制台入口</th>
              <th>后端边界</th>
              <th>用户得到什么</th>
            </tr>
          </thead>
          <tbody>
            {capabilityRows.map((row) => (
              <tr key={row.domain}>
                <td>{row.domain}</td>
                <td>{row.console}</td>
                <td>
                  <code>{row.backend}</code>
                </td>
                <td>{row.outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function ModelRuntimeSection() {
  return (
    <section id="models" className="docs-section">
      <h2>模型与运行模式</h2>
      <p>
        模型调用集中在后端，前端只负责配置和触发。这样可以避免 API Key 暴露，同时让 mock、真实供应商和自动模式共用同一套会话链路。
      </p>
      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>模式</th>
              <th>适用场景</th>
              <th>边界说明</th>
            </tr>
          </thead>
          <tbody>
            {runtimeEntries.map((entry) => (
              <tr key={entry.name}>
                <td>
                  <code>{entry.name}</code>
                </td>
                <td>{entry.usage}</td>
                <td>{entry.boundary}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="docs-note-grid">
        <article id="reasoning">
          <BranchesOutlined />
          <h3>Reasoning 与流式输出</h3>
          <p>支持在会话中打开思考模式，后端会把 reasoning 内容作为可折叠块流式同步到前端。</p>
        </article>
        <article id="queue">
          <CloudServerOutlined />
          <h3>队列与重试</h3>
          <p>长任务进入后台队列，顶部任务按钮可查看、刷新或取消；高并发时建议前端保持幂等重试。</p>
        </article>
      </div>
    </section>
  );
}

export function WorkflowNodeSection() {
  return (
    <section id="workflow-nodes" className="docs-section docs-workflow-nodes">
      <div className="docs-section-head">
        <BranchesOutlined />
        <div>
          <h2>工作流节点说明</h2>
          <p>
            群聊运行时不会把任务交给隐藏的总控 Agent，而是优先读取当前会话保存的 workflow。每个节点都有明确输入、配置和运行态，方便复盘失败节点。
          </p>
        </div>
      </div>
      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>节点</th>
              <th>用途</th>
              <th>关键配置</th>
              <th>运行输出</th>
            </tr>
          </thead>
          <tbody>
            {workflowNodeDocs.map((node) => (
              <tr key={node.type}>
                <td>
                  <code>{node.type}</code>
                </td>
                <td>{node.purpose}</td>
                <td>{node.config}</td>
                <td>{node.output}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="docs-callout">
        画布保存后写入 conversation.extra.workflow；运行后产生 WorkflowRun，节点状态会记录 status、progress、message、output、started_at 和 completed_at。
      </div>
    </section>
  );
}

export function ApiDetailsSection() {
  return (
    <section id="api-overview" className="docs-section docs-api-detail">
      <div className="docs-section-head">
        <ApiOutlined />
        <div>
          <h2>API 总览</h2>
          <p>平台 API 按认证、工作区、会话消息、能力目录、文件产物和运行任务拆分，前端通过 `src/api` 统一封装。</p>
        </div>
      </div>
      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>模块</th>
              <th>入口</th>
              <th>用途</th>
            </tr>
          </thead>
          <tbody>
            {endpointEntries.map((entry) => (
              <tr key={entry.endpoint}>
                <td>{entry.module}</td>
                <td>
                  <code>{entry.endpoint}</code>
                </td>
                <td>{entry.purpose}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function AssetLifecycleSection() {
  return (
    <section id="asset-lifecycle" className="docs-section docs-asset-band">
      <div className="docs-section-head">
        <FileProtectOutlined />
        <div>
          <h2>文件、知识库与产物生命周期</h2>
          <p>
            AgentHub 的文件不是临时附件，而是工作区上下文的一部分。上传、预览、抽取、知识库检索、工具执行和产物交付都会尽量保留可追踪记录。
          </p>
        </div>
      </div>
      <div className="docs-lifecycle-grid">
        {assetLifecycleEntries.map((entry) => (
          <article key={entry.title}>
            <strong>{entry.title}</strong>
            <p>{entry.detail}</p>
          </article>
        ))}
      </div>
      <div className="docs-note-grid docs-wide-notes">
        <article id="files">
          <FileProtectOutlined />
          <h3>文件与知识库</h3>
          <p>文件可作为会话附件，也可以通过知识库导入后被检索；上下文层会负责摘要、变量和记忆拼装。</p>
        </article>
        <article id="artifacts">
          <CodeOutlined />
          <h3>产物预览与导出</h3>
          <p>产物卡片只在需要交付内容时出现，点击后进入右侧预览，可编辑、保存版本、Diff、导出。</p>
        </article>
        <article id="deploy">
          <CloudServerOutlined />
          <h3>部署预览</h3>
          <p>HTML 和 Web App 类产物可以创建部署预览记录，后续可在部署模块查看状态和回滚入口。</p>
        </article>
      </div>
    </section>
  );
}

export function IntegrationSection() {
  return (
    <section id="integration" className="docs-section docs-two-column">
      <div>
        <h2>AI Coding 与能力接入</h2>
        <p>
          AgentHub 的扩展方式接近主流 API 文档站的接入指南：先确认兼容协议或能力来源，再绑定凭证和权限，最后在会话或 workflow 中验证。
        </p>
        <ol className="docs-numbered-list">
          {integrationSteps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
      <CodePanel title="workflow 片段" code={workflowExampleCode} />
      <div className="docs-note-grid docs-wide-notes">
        <article id="custom-tools">
          <ToolOutlined />
          <h3>自定义工具</h3>
          <p>工具定义保存到数据库，受限 Python 片段落在工作区目录内，调用前经过参数校验和权限检查。</p>
        </article>
        <article id="skills">
          <CodeOutlined />
          <h3>Skill 包</h3>
          <p>Skill 可以手动创建、AI 生成或从 MCP 导入，并按 Agent 权限进行绑定。</p>
        </article>
        <article id="mcp">
          <SafetyCertificateOutlined />
          <h3>MCP 服务</h3>
          <p>支持 HTTP 与 stdio 注册、探测、调用和记录，适合接入外部工具与上下文服务。</p>
        </article>
      </div>
    </section>
  );
}

export function TroubleshootingSection() {
  return (
    <section id="faq" className="docs-section docs-faq-band">
      <h2>常见问题与排查入口</h2>
      <div className="docs-table-wrap">
        <table className="docs-table">
          <thead>
            <tr>
              <th>现象</th>
              <th>建议检查</th>
            </tr>
          </thead>
          <tbody>
            {troubleshootingRows.map(([title, detail]) => (
              <tr key={title}>
                <td>{title}</td>
                <td>{detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div id="usage" className="docs-callout">
        后台任务、消息流和产物导出都可以从控制台观察运行态；生产环境建议同步查看审计日志和后端服务日志。
      </div>
    </section>
  );
}

export function UpdatesSection() {
  return (
    <section id="updates" className="docs-section docs-updates">
      <h2>更新日志</h2>
      <ul>
        {updateItems.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
      <p>更新时间：2026 年 05 月 29 日</p>
    </section>
  );
}
