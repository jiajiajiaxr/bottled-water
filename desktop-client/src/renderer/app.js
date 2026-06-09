const desktop = window.agentHubDesktop ?? createBrowserFallback();

const state = {
  vault: [],
  agent: {
    running: false,
    logs: [],
  },
};

const views = {
  command: document.querySelector("#commandView"),
  files: document.querySelector("#filesView"),
  agent: document.querySelector("#agentView"),
  settings: document.querySelector("#settingsView"),
};

function $(selector) {
  return document.querySelector(selector);
}

function setView(name) {
  Object.entries(views).forEach(([key, element]) => {
    element.classList.toggle("hidden", key !== name);
  });
  document.querySelectorAll(".rail-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === name);
  });
}

function renderVault() {
  const list = $("#vaultList");
  if (!state.vault.length) {
    list.innerHTML = `
      <div class="empty-state">
        <strong>还没有本地文件</strong>
        <p>点击右上角按钮选择文件，桌面端会加密复制到本地 vault。</p>
      </div>
    `;
    return;
  }

  list.innerHTML = state.vault
    .map(
      (item) => `
        <button class="vault-item" data-id="${item.id}">
          <span class="file-kind">${item.classification}</span>
          <strong>${escapeHtml(item.filename)}</strong>
          <small>${formatSize(item.size)} · ${new Date(item.imported_at).toLocaleString()}</small>
        </button>
      `,
    )
    .join("");

  list.querySelectorAll(".vault-item").forEach((button) => {
    button.addEventListener("click", () => previewVaultFile(button.dataset.id));
  });
}

function renderAgent() {
  const badge = $("#agentBadge");
  badge.textContent = state.agent.running ? "Running" : "Idle";
  badge.className = `badge ${state.agent.running ? "running" : "idle"}`;
  $("#agentPid").textContent = state.agent.pid ? `PID ${state.agent.pid}` : "PID 未分配";
  $("#agentStartedAt").textContent = state.agent.startedAt
    ? `启动时间：${new Date(state.agent.startedAt).toLocaleString()}`
    : "等待启动后台任务守护进程。";
  $("#agentLogs").textContent = state.agent.logs?.length
    ? state.agent.logs.join("\n")
    : "暂无 Agent 日志。";
}

async function previewVaultFile(id) {
  const preview = await desktop.files.preview(id);
  $("#previewFileName").textContent = preview.item.filename;
  $("#filePreview").textContent =
    preview.previewText || preview.previewNote || "该文件暂无可展示文本。";
}

async function loadState() {
  const next = await desktop.getState();
  state.vault = next.vault || [];
  state.agent = next.agent || state.agent;
  $("#apiBaseInput").value = next.apiBase || $("#apiBaseInput").value;
  renderVault();
  renderAgent();
  checkHealth();
}

async function checkHealth() {
  const text = $("#apiStatusText");
  try {
    const payload = await desktop.api.health($("#apiBaseInput").value);
    text.textContent = payload?.data?.status === "ok" || payload?.status === "ok" ? "后端在线" : "后端已响应";
    text.parentElement.classList.add("ok");
  } catch {
    text.textContent = "后端未连接";
    text.parentElement.classList.remove("ok");
  }
}

async function importFiles() {
  const imported = await desktop.files.importEncrypted();
  if (imported.length) {
    state.vault = [...imported, ...state.vault];
    renderVault();
    desktop.notifications.show({
      title: "本地文件已加密纳管",
      body: `已处理 ${imported.length} 个文件，可继续上传或预览。`,
    });
  }
}

async function startAgent() {
  state.agent = await desktop.agent.start();
  renderAgent();
  setView("agent");
}

async function stopAgent() {
  state.agent = await desktop.agent.stop();
  renderAgent();
}

function wireEvents() {
  document.querySelectorAll(".rail-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  $("#notifyButton").addEventListener("click", () =>
    desktop.notifications.show({
      title: "AgentHub Desktop",
      body: "系统通知通道正常，可用于任务完成和审批提醒。",
    }),
  );
  $("#startAgentButton").addEventListener("click", startAgent);
  $("#stopAgentButton").addEventListener("click", stopAgent);
  $("#agentRefreshButton").addEventListener("click", async () => {
    state.agent = await desktop.agent.status();
    renderAgent();
  });
  $("#importFilesButton").addEventListener("click", importFiles);
  $("#healthButton").addEventListener("click", checkHealth);

  desktop.agent.onLog?.((line) => {
    state.agent.logs = [line, ...(state.agent.logs || [])].slice(0, 80);
    renderAgent();
  });
  desktop.agent.onStatus?.((status) => {
    state.agent = status;
    renderAgent();
  });
}

function formatSize(size) {
  if (!size) return "0 B";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function createBrowserFallback() {
  const fallbackLogs = [];
  return {
    getState: async () => ({
      apiBase: "http://127.0.0.1:8000/api/v1",
      vault: [
        {
          id: "demo",
          filename: "课题研发资料.md",
          size: 4280,
          classification: "code",
          imported_at: new Date().toISOString(),
        },
      ],
      agent: { running: false, logs: fallbackLogs },
    }),
    files: {
      importEncrypted: async () => [],
      preview: async () => ({
        item: { filename: "课题研发资料.md" },
        previewText: "# 本地预览\n\n浏览器预览模式下展示示例内容；Electron 环境会读取加密 vault。",
      }),
    },
    notifications: { show: async () => true },
    agent: {
      start: async () => {
        fallbackLogs.unshift(JSON.stringify({ event: "agent.started", detail: { mode: "browser-demo" } }));
        return { running: true, pid: "demo", startedAt: new Date().toISOString(), logs: fallbackLogs };
      },
      stop: async () => ({ running: false, logs: fallbackLogs }),
      status: async () => ({ running: false, logs: fallbackLogs }),
      onLog: () => () => undefined,
      onStatus: () => () => undefined,
    },
    api: {
      health: async (apiBase) => {
        const response = await fetch(`${apiBase}/health`);
        return response.json();
      },
    },
  };
}

wireEvents();
loadState();
