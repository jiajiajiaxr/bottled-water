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
            AgentHub 是围绕 IM 协作组织的多 Agent 工作台。它不是把多个聊天机器人简单放在同一个页面里，而是把会话、工作区、Agent 能力、工作流、文件产物和安全治理放在同一套产品链路里。用户从输入需求开始，平台会逐步组织上下文、选择角色、调用工具、记录运行态，并把结果沉淀为可预览、可导出、可审计的产物。
          </p>
          <p>
            当前版本把简单聊天和复杂协作拆开处理：新建会话默认只选择 Daily Chat Agent；当用户手动加入多个 Agent 并提出复杂任务时，Team Leader 会生成短任务计划、选择合适角色、汇总真实产物；需要稳定复用的流程则保存为 workflow。阅读文档时建议先理解这些模块之间的关系，再进入具体 API 或源码位置。
          </p>
        </div>
      </div>
      <div className="docs-explain-strip">
        <span>输入</span>
        <strong>需求、附件、知识片段、工作区变量</strong>
        <span>执行</span>
        <strong>Agent、工具、Skill、MCP、workflow</strong>
        <span>交付</span>
        <strong>消息、Artifact、导出文件、部署预览、审计记录</strong>
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
      <div className="docs-checklist-band">
        <h3>判断一个能力是否应该进入 AgentHub</h3>
        <ul>
          <li>它是否需要读取工作区上下文，而不是只处理一段孤立文本。</li>
          <li>它是否会产生可复用的角色、工具、工作流节点或可交付产物。</li>
          <li>它是否需要权限控制、审计记录、运行状态或失败复盘。</li>
          <li>它是否能被多个会话、多个 Agent 或多个项目重复使用。</li>
        </ul>
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
          AgentHub 的最小闭环是：登录、选择工作区、创建会话、选择 Agent、发送消息、查看流式回复和可选产物。单聊直接运行当前 Agent 的小循环；群聊默认由 Team Leader 组织协作，启用 workflow 后才按会话内保存的画布执行。
        </p>
        <p>
          首次体验时不要急着配置所有模块。建议先用默认 Daily Chat Agent 跑一句普通对话，确认流式消息稳定；再手动选择多个官方 Agent 跑一个可观察的小任务，例如“生成一份发布材料、复核并给出预览产物”。这个任务足够小，可以快速暴露登录、工作区、文件上传、消息流、工具调用、协作进度和产物预览是否贯通；同时又足够完整，能展示 AgentHub 相比普通聊天界面的差异。
        </p>
        <ol className="docs-numbered-list">
          <li>使用演示用户进入控制台，确认左上角已经选择目标工作区。工作区决定文件、会话、产物和运行记录的归属。</li>
          <li>新建会话默认会选择 Daily Chat Agent。普通聊天保持单 Agent；复杂任务再手动增加 Frontend、Writing、Reviewer、Deploy 等合适角色。</li>
          <li>上传文件或输入需求，发送后观察消息是否持续流式回填。若任务较长，顶部后台任务入口应该能看到运行状态。</li>
          <li>复杂群聊应看到短任务进度和 Agent 报告；展开工具摘要，确认工具调用目的、参数和结果是否清楚。如果 Agent 没有调用工具，要回到 Agent 权限和工具 schema 检查。</li>
          <li>如果出现产物卡片，点击后在右侧预览、编辑、Diff 或导出。产物链路是判断“交付是否真实落地”的关键。</li>
        </ol>
        <div className="docs-runbook-note">
          <strong>验收标准</strong>
          <span>一次成功的首跑应同时看到：用户消息、Agent 流式回复、必要的工具摘要、稳定的任务状态；复杂群聊还应看到协作进度、按需 Team Leader 聚合交付，以及可打开的产物或明确的非产物结论。</span>
        </div>
      </div>
      <div id="frontend-sdk">
        <CodePanel title="前端 SDK 调用示例" code={apiExampleCode} />
      </div>
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
            下表按产品控制台入口梳理能力边界。排查问题时先定位用户正在使用的控制台区域，再顺着后端 API 和服务层查运行记录。这样可以避免把模型问题误判成前端问题，或把文件权限问题误判成 Agent 回复质量问题。
          </p>
        </div>
      </div>
      <div className="docs-map-notes">
        <article>
          <strong>先看入口</strong>
          <p>用户从哪里触发操作，通常决定应先查哪个前端组件和 API 模块。</p>
        </article>
        <article>
          <strong>再看边界</strong>
          <p>确认数据属于哪个工作区、哪个会话、哪个 Agent，以及是否需要权限授权。</p>
        </article>
        <article>
          <strong>最后看记录</strong>
          <p>消息、任务、工具调用、WorkflowRun 和审计日志共同构成可复盘证据。</p>
        </article>
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
        模型调用集中在后端，前端只负责配置和触发。这样可以避免 API Key 暴露，同时让 mock、真实供应商和自动模式共用同一套会话链路。前端看到的是统一的消息流、工具摘要和运行态；后端负责决定真实模型、mock 模式或自动模式如何落地。
      </p>
      <p>
        在开发环境中，mock 模式用于保证没有密钥时也能完整验证 UI、路由、消息状态和基础编排；在演示或生产环境中，真实供应商模式负责接入外部模型推理；auto 模式则适合团队共享环境，根据后端配置自动选择可用路径。无论是哪一种模式，前端都不应该直接持有模型密钥。
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
          <p>支持在会话中打开思考模式，后端会把 reasoning 内容作为可折叠块流式同步到前端。产品上应让用户区分“正在思考”“正在调用工具”“正在写最终回复”这几类状态，避免把内部推理和最终结论混在一起。</p>
        </article>
        <article id="queue">
          <CloudServerOutlined />
          <h3>队列与重试</h3>
          <p>长任务进入后台队列，顶部任务按钮可查看、刷新或取消；高并发时建议前端保持幂等重试。调试时要同时看任务状态、消息流状态和最终消息写入状态，三者不一致时通常意味着实时事件或 finalizer 环节需要检查。</p>
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
            群聊运行时有两条路径：未启用 workflow 时，Team Leader 作为普通调度 Agent 规划任务、选择合适成员并汇总真实结果；启用 workflow 后，当前会话保存的画布成为执行计划。每个节点都有明确输入、配置和运行态，方便复盘失败节点。设计 workflow 时，重点不是把所有人工判断都流程化，而是把那些需要稳定复用、需要多人协作、需要生成产物或需要审计的步骤显式写出来。
          </p>
        </div>
      </div>
      <div className="docs-flow-guide">
        <div>
          <span>1</span>
          <strong>先定义输入</strong>
          <p>明确用户输入、附件摘要和工作区变量如何进入 start 节点。</p>
        </div>
        <div>
          <span>2</span>
          <strong>再分配责任</strong>
          <p>让 agent、tool、skill、mcp 节点各自负责一类可验证动作。</p>
        </div>
        <div>
          <span>3</span>
          <strong>最后收束交付</strong>
          <p>用 review、artifact、end 节点完成质量检查、产物生成和最终回复。</p>
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
        画布保存后写入 conversation.extra.workflow；启用后会更新会话运行模式。运行后产生 WorkflowRun，节点状态会记录 status、progress、message、output、started_at 和 completed_at。未启用 workflow 的复杂群聊则看 scheduler.plan、agent.report 和 scheduler.summary。
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
          <p>平台 API 按认证、工作区、会话消息、能力目录、文件产物和运行任务拆分，前端通过 `src/api` 统一封装。新增页面时不要直接在组件里散写请求，先补 API 方法和类型，再让 UI 消费稳定的 SDK。</p>
          <p>排查接口问题时可以按三层看：浏览器请求是否发出、API 是否返回符合前端期望的数据结构、后端 service 是否把数据写入正确的工作区或运行记录。只有这三层都一致，页面上的会话、产物和任务状态才会稳定。</p>
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
      <div className="docs-note-grid docs-wide-notes">
        <article>
          <SafetyCertificateOutlined />
          <h3>认证方式</h3>
          <p>
            前端登录后保存访问令牌，后续请求统一经过 `src/api/client.ts` 注入认证头；后端只从服务端环境读取模型密钥。登录失效时要同时检查本地 token、后端用户状态和 API 响应码。
          </p>
        </article>
        <article>
          <CloudServerOutlined />
          <h3>实时事件</h3>
          <p>
            会话消息、后台任务和工具运行态通过 SSE 或 WebSocket 同步；调试流式问题时先看 messages API 和 realtime 服务，再确认前端 Store 是否正确合并事件。
          </p>
        </article>
        <article>
          <CodeOutlined />
          <h3>前端封装</h3>
          <p>
            新增接口时优先补 `frontend/src/api` 的类型化方法，再让页面组件调用封装后的 SDK。这样可以让错误处理、认证头、响应结构和测试方式保持一致。
          </p>
        </article>
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
          <p>
            文件和产物要分开理解：文件通常是用户输入、上下文来源或项目资料；产物是 Agent 生成并准备交付给用户的结果。文件是否被正确解析，影响 Agent 能不能理解任务；产物是否能预览、导出和回滚，影响结果能不能被真正使用。
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
          <p>文件可作为会话附件，也可以通过知识库导入后被检索；上下文层会负责摘要、变量和记忆拼装。大文件和 Office 文件应优先走后端预览和抽取链路，避免把完整内容直接塞进前端状态。</p>
        </article>
        <article id="artifacts">
          <CodeOutlined />
          <h3>产物预览与导出</h3>
          <p>产物卡片只在需要交付内容时出现，点击后进入右侧预览，可编辑、保存版本、Diff、导出。文档类产物要关注内容结构，Web 类产物要关注依赖、预览地址和部署记录。</p>
        </article>
        <article id="deploy">
          <CloudServerOutlined />
          <h3>部署预览</h3>
          <p>HTML 和 Web App 类产物可以创建部署预览记录，后续可在部署模块查看状态和回滚入口。预览失败时，先确认 Artifact 文件路径，再确认部署记录和静态资源是否完整。</p>
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
          AgentHub 的扩展方式接近主流 API 文档站的接入指南：先确认兼容协议或能力来源，再绑定凭证和权限，最后在会话、Team Leader 调度或 workflow 中验证。接入新能力时不要只追求“能调通”，还要确认结果是否能进入消息、产物、任务或审计记录，否则用户很难理解这个能力是否真的执行成功。
        </p>
        <ol className="docs-numbered-list">
          {integrationSteps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <div className="docs-callout">
          接入新能力时先确认三件事：谁可以调用、运行结果写入哪里、失败后用户从哪个界面看到原因。
        </div>
      </div>
      <CodePanel title="workflow 片段" code={workflowExampleCode} />
      <div className="docs-note-grid docs-wide-notes">
        <article id="custom-tools">
          <ToolOutlined />
          <h3>自定义工具</h3>
          <p>工具定义保存到数据库，受限 Python 片段落在工作区目录内，调用前经过参数校验和权限检查。适合封装明确输入输出的小能力，例如读取项目文件、转换数据、调用内部 HTTP API 或生成结构化片段。</p>
        </article>
        <article id="external-agents">
          <CodeOutlined />
          <h3>外部 Coding Agent</h3>
          <p>Codex、Claude Code 和兼容适配器通过 external_agent.invoke 统一调用，支持 run、probe、status、cancel，运行事实写入外部 Agent 记录。用户可见结论必须以记录状态、stdout/stderr、变更文件和退出码为准。</p>
        </article>
        <article id="skills">
          <CodeOutlined />
          <h3>Skill 包</h3>
          <p>Skill 可以手动创建、AI 生成或从 MCP 导入，并按 Agent 权限进行绑定。它更适合沉淀一类可复用方法论或执行流程，而不是一次性的工具脚本。</p>
        </article>
        <article id="mcp">
          <SafetyCertificateOutlined />
          <h3>MCP 服务</h3>
          <p>支持 HTTP 与 stdio 注册、探测、调用和记录，适合接入外部工具与上下文服务。上线前至少要验证 probe、工具列表、参数 schema、失败返回和调用日志。</p>
        </article>
        <article id="sandbox">
          <CloudServerOutlined />
          <h3>沙箱执行</h3>
          <p>命令运行被限制在工作区边界内，高风险能力需要经过权限校验并写入审计记录。沙箱适合运行检查、构建、格式化或小型脚本，不应绕过工作区隔离去访问任意系统路径。</p>
        </article>
      </div>
    </section>
  );
}

export function TroubleshootingSection() {
  return (
    <section id="faq" className="docs-section docs-faq-band">
      <h2>常见问题与排查入口</h2>
      <p>
        排查时先定位问题发生在哪条链路：登录与权限、模型调用、消息流、工具执行、工作流节点、文件预览、产物导出或部署预览。不要一开始就只看前端页面，很多问题需要同时检查浏览器控制台、API 响应、后台任务、实时事件和审计日志。
      </p>
      <div className="docs-triage-lane">
        <span>用户入口</span>
        <span>API 响应</span>
        <span>运行事件</span>
        <span>数据记录</span>
        <span>审计日志</span>
      </div>
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
        排查顺序建议：先确认用户入口和工作区，再看浏览器控制台、前端 Store、后端 API 响应、实时事件、任务记录和审计日志。
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
      <p>更新时间：2026 年 06 月 08 日</p>
    </section>
  );
}
