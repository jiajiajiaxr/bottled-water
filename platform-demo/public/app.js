const staticTimeline = [
  [0, 0, "等待调度", "Team Leader", "queued", ""],
  [600, 8, "Team Leader 正在拆解任务", "Team Leader", "running", "生成 Web、桌面、移动三端联调计划。"],
  [1300, 23, "Frontend Worker 正在生成操作界面", "Frontend Worker", "running", "构建 IM、成果预览和部署核验演示流。"],
  [2100, 42, "Backend Worker 正在准备调试 API", "Backend Worker", "running", "提供健康检查、运行记录和事件流。"],
  [3100, 66, "QA Reviewer 正在核验部署闭环", "QA Reviewer", "running", "验证本地一键启动和预览卡片。"],
  [4300, 88, "正在生成成果预览卡", "Frontend Worker", "completed", "完成平台实操 Demo 页面。"],
  [5600, 100, "任务完成", "QA Reviewer", "completed", "Demo 已可静态发布、预览和验收。"],
];

const initialAgents = [
  { name: "Team Leader", status: "queued", work_product: "" },
  { name: "Frontend Worker", status: "queued", work_product: "" },
  { name: "Backend Worker", status: "queued", work_product: "" },
  { name: "QA Reviewer", status: "queued", work_product: "" },
];

const elements = {
  localUrl: document.querySelector("#localUrl"),
  publishMode: document.querySelector("#publishMode"),
  backendDot: document.querySelector("#backendDot"),
  backendStatus: document.querySelector("#backendStatus"),
  backendMeta: document.querySelector("#backendMeta"),
  startRun: document.querySelector("#startRun"),
  runStatus: document.querySelector("#runStatus"),
  runId: document.querySelector("#runId"),
  progressMeter: document.querySelector("#progressMeter"),
  agentList: document.querySelector("#agentList"),
  chatList: document.querySelector("#chatList"),
  artifactTitle: document.querySelector("#artifactTitle"),
  artifactFrame: document.querySelector("#artifactFrame"),
  debugLog: document.querySelector("#debugLog"),
};

const state = {
  apiMode: false,
  currentRun: undefined,
  eventSource: undefined,
};

elements.localUrl.textContent = window.location.href;
elements.startRun.addEventListener("click", startRun);

renderRun(createStaticRun("demo-ready"));
renderArtifact(createArtifact("artifact-static", "静态演示已就绪。点击启动任务后会生成完整成果预览。"));
hydrate();

async function hydrate() {
  const health = await probeLocalDemoApi();
  state.apiMode = Boolean(health);

  elements.publishMode.textContent = state.apiMode ? "本地联调模式" : "GitHub Pages 静态模式";
  elements.backendStatus.textContent = state.apiMode
    ? `Demo API 在线 · ${health.status}`
    : "静态演示模式";
  elements.backendMeta.textContent = state.apiMode
    ? "当前页面正在使用本地 /api 调试接口"
    : "无需后端，浏览器内置模拟任务流";
  elements.backendDot.className = `dot ${state.apiMode ? "ok" : ""}`;
  appendLog(state.apiMode ? "已连接本地 Demo API。" : "未检测到本地 Demo API，使用纯静态模拟。");
}

async function probeLocalDemoApi() {
  if (location.protocol === "file:") return undefined;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 900);
  try {
    const response = await fetch(new URL("./health", location.href), {
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) return undefined;
    const payload = await response.json();
    return payload?.service === "agenthub-platform-demo" ? payload : undefined;
  } catch {
    return undefined;
  } finally {
    window.clearTimeout(timer);
  }
}

async function startRun() {
  elements.startRun.disabled = true;
  resetChat();

  if (state.apiMode) {
    await startApiRun();
  } else {
    startStaticRun();
  }
}

async function startApiRun() {
  appendLog("POST ./api/runs");
  const run = await postJson("./api/runs", {});
  state.currentRun = run;
  renderRun(run);
  appendMessage("Team Leader", "收到，开始联调本地 Demo API 和多 Agent 任务流。", "incoming");
  connectRunEvents(run.id);
}

function startStaticRun() {
  const run = createStaticRun(`static-${Date.now().toString(36)}`);
  state.currentRun = run;
  renderRun(run);
  appendLog("启动浏览器端静态任务模拟。");
  appendMessage("Team Leader", "收到，开始静态模拟多 Agent 协同交付。", "incoming");

  for (const [delay, progress, step, agentName, agentStatus, product] of staticTimeline.slice(1)) {
    window.setTimeout(() => {
      updateRun(run, progress, step, agentName, agentStatus, product);
      renderRun(run);
      appendLog(`${progress}% ${step}: ${product}`);
      appendMessage(progress >= 100 ? "QA Reviewer" : "AgentHub Runtime", `${step}：${product}`, progress >= 100 ? "outgoing" : "incoming muted");

      if (progress >= 100) {
        renderArtifact(
          createArtifact(run.id, "平台实操 Demo 已完成，可直接静态发布到 GitHub Pages，也可本地一键联调。"),
        );
        elements.startRun.disabled = false;
      }
    }, delay);
  }
}

function connectRunEvents(runId) {
  state.eventSource?.close();
  state.eventSource = new EventSource(`./api/runs/${runId}/events`);

  state.eventSource.addEventListener("run.progress", (event) => {
    const payload = JSON.parse(event.data);
    renderRun(payload.run);
    appendLog(`${payload.run.progress}% ${payload.event.message}`);
    appendMessage("AgentHub Runtime", payload.event.message, "incoming muted");
  });

  state.eventSource.addEventListener("run.completed", async (event) => {
    const payload = JSON.parse(event.data);
    renderRun(payload.run);
    appendLog(`${payload.run.progress}% ${payload.event.message}`);
    appendMessage("QA Reviewer", "验证通过：一键启动、事件流、成果预览均可用。", "outgoing");
    state.eventSource.close();
    elements.startRun.disabled = false;

    try {
      renderArtifact(await getJson("./api/artifacts/latest"));
    } catch {
      renderArtifact(createArtifact(payload.run.id, "联调任务完成，成果预览已生成。"));
    }
  });

  state.eventSource.onerror = () => {
    appendLog("事件流中断，切回静态模拟收尾。");
    state.eventSource.close();
    elements.startRun.disabled = false;
  };
}

function createStaticRun(id) {
  return {
    id,
    status: "queued",
    progress: 0,
    current_step: "等待调度",
    agents: initialAgents.map((agent) => ({ ...agent })),
  };
}

function updateRun(run, progress, step, agentName, agentStatus, product) {
  run.progress = progress;
  run.current_step = step;
  run.status = progress >= 100 ? "completed" : "running";
  if (progress >= 100) {
    run.agents = run.agents.map((item) => ({
      ...item,
      status: item.work_product ? "completed" : item.status,
    }));
  }
  const agent = run.agents.find((item) => item.name === agentName);
  if (agent) {
    agent.status = agentStatus;
    agent.work_product = product;
  }
}

function renderRun(run) {
  elements.runStatus.textContent = `${run.status} · ${run.current_step}`;
  elements.runId.textContent = run.id;
  elements.progressMeter.value = run.progress;
  elements.agentList.innerHTML = run.agents
    .map(
      (agent) => `
        <li>
          <span class="agent-badge ${agent.status}">${escapeHtml(agent.status)}</span>
          <div>
            <strong>${escapeHtml(agent.name)}</strong>
            <p>${escapeHtml(agent.work_product || "等待任务分配")}</p>
          </div>
        </li>
      `,
    )
    .join("");
}

function renderArtifact(artifact) {
  elements.artifactTitle.textContent = artifact.title;
  elements.artifactFrame.srcdoc = `
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="UTF-8" />
        <style>
          body { margin: 0; padding: 22px; font-family: Inter, "Microsoft YaHei", sans-serif; background: #f6f8fc; color: #111827; }
          h1 { margin: 0 0 10px; font-size: 24px; letter-spacing: 0; }
          p { color: #475569; line-height: 1.7; }
          ul { display: grid; gap: 8px; margin: 18px 0 0; padding: 0; list-style: none; }
          li { padding: 10px 12px; border: 1px solid #d9e2ef; border-radius: 8px; background: #ffffff; color: #334155; }
          .artifact-document { max-width: 720px; }
        </style>
      </head>
      <body>${artifact.preview_html}</body>
    </html>
  `;
}

function createArtifact(id, summary) {
  return {
    id,
    title: "AgentHub 平台实操 Demo 成果",
    kind: "html",
    summary,
    preview_html: `
      <article class="artifact-document">
        <h1>AgentHub 平台实操 Demo</h1>
        <p>${escapeHtml(summary)}</p>
        <ul>
          <li>Web 工作台同款三栏布局</li>
          <li>多 Agent 协作进度模拟</li>
          <li>成果产物右侧预览</li>
          <li>本地 API 自动探测</li>
          <li>GitHub Pages 纯静态托管</li>
        </ul>
      </article>
    `,
  };
}

function resetChat() {
  elements.chatList.innerHTML = "";
}

function appendMessage(author, text, type) {
  const item = document.createElement("div");
  item.className = `bubble ${type}`;
  item.innerHTML = `<strong>${escapeHtml(author)}</strong><p>${escapeHtml(text)}</p>`;
  elements.chatList.appendChild(item);
  elements.chatList.scrollTop = elements.chatList.scrollHeight;
}

function appendLog(line) {
  const prefix = new Date().toLocaleTimeString();
  elements.debugLog.textContent =
    elements.debugLog.textContent === "等待运行。"
      ? `[${prefix}] ${line}`
      : `${elements.debugLog.textContent}\n[${prefix}] ${line}`;
  elements.debugLog.scrollTop = elements.debugLog.scrollHeight;
}

async function getJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
