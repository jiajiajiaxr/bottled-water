const desktop = window.agentHubDesktop;
const app = document.querySelector("#app");
const params = new URLSearchParams(window.location.search);
const mode = params.get("mode") || "fallback";

let config = {
  webAppUrl: params.get("webAppUrl") || "http://127.0.0.1:5174",
  globalShortcut: "Alt+Space",
  quickCaptureShortcut: "Alt+Shift+Space",
};

async function boot() {
  config = { ...config, ...((await desktop?.getConfig?.()) || {}) };
  if (mode === "titlebar") {
    renderTitlebar();
  } else if (mode === "quick") {
    renderQuickInput();
  } else if (mode === "capture") {
    renderCaptureOverlay();
  } else {
    renderFallback();
  }
}

function renderTitlebar() {
  app.className = "titlebar-shell";
  app.innerHTML = `
    <header class="app-titlebar">
      <div class="traffic-zone">
        <button class="nav-icon menu-dot" title="AgentHub">A</button>
        <button class="nav-icon" data-nav="back" title="后退">‹</button>
        <button class="nav-icon" data-nav="forward" title="前进">›</button>
        <button class="nav-icon reload" data-nav="reload" title="刷新">↻</button>
      </div>
      <nav class="desktop-actions" aria-label="桌面增强">
        <button data-action="quick">悬浮输入</button>
        <button data-action="screen">截图问答</button>
        <button data-action="copy">复制链接</button>
      </nav>
      <div class="drag-region">
        <span id="windowTitle">AgentHub</span>
      </div>
      <div class="status-zone">
        <span class="live-dot"></span>
        <strong>AgentHub 0.1.0</strong>
      </div>
      <div class="window-controls">
        <button data-window="minimize" title="最小化">−</button>
        <button data-window="maximize" title="最大化">□</button>
        <button data-window="close" title="关闭">×</button>
      </div>
    </header>
  `;

  document.querySelectorAll("[data-nav]").forEach((button) => {
    button.addEventListener("click", () => desktop.navigation(button.dataset.nav));
  });
  document.querySelectorAll("[data-window]").forEach((button) => {
    button.addEventListener("click", () => desktop.windowControl(button.dataset.window));
  });
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => handleTitlebarAction(button.dataset.action));
  });
  desktop.onNavigationState?.(updateNavigationState);
  desktop.onTitleUpdated?.((title) => {
    const titleNode = document.querySelector("#windowTitle");
    if (titleNode) titleNode.textContent = title || "AgentHub";
  });
  desktop.onWindowState?.((state) => updateNavigationState(state));
}

function renderFallback() {
  app.className = "desktop-fallback";
  app.innerHTML = `
    <section class="fallback-card">
      <div class="brand-row">
        <span class="brand-mark">A</span>
        <div>
          <p class="eyebrow">AgentHub Desktop</p>
          <h1>轻量桌面客户端</h1>
        </div>
      </div>
      <p class="lead">桌面端直接承载 Web 主端，因此账号、对话、文件、模型能力和会员权益保持完全一致。当前只是没有连上 Web 地址。</p>

      <label class="field">
        <span>Web 主端地址</span>
        <input id="webAppUrlInput" value="${escapeHtml(config.webAppUrl)}" />
      </label>

      <div class="button-row">
        <button id="reloadButton" class="primary-button">重新打开</button>
        <button id="saveButton" class="ghost-button">保存地址</button>
      </div>

      <div class="feature-grid">
        <article><strong>全局唤起</strong><span>${escapeHtml(config.globalShortcut || "Alt+Space")} 呼出悬浮输入框</span></article>
        <article><strong>后台常驻</strong><span>关闭主窗口后可留在托盘</span></article>
        <article><strong>多窗口</strong><span>对话可拆到独立窗口并行处理</span></article>
        <article><strong>系统通知</strong><span>任务完成后使用原生通知提醒</span></article>
      </div>
    </section>
  `;

  document.querySelector("#saveButton").addEventListener("click", saveUrl);
  document.querySelector("#reloadButton").addEventListener("click", async () => {
    await saveUrl();
    await desktop.reloadWeb();
  });
}

function renderQuickInput() {
  app.className = "quick-shell";
  app.innerHTML = `
    <section class="quick-panel">
      <div class="quick-head">
        <span class="brand-mark">A</span>
        <div>
          <strong>AgentHub 快捷输入</strong>
          <small id="quickHint">${escapeHtml(config.globalShortcut || "Alt+Space")} 呼出，Enter 发送到主窗口</small>
        </div>
      </div>
      <form id="quickForm" class="quick-form">
        <input id="quickInput" placeholder="输入问题、指令、要改写/翻译的文字..." autofocus />
        <button>发送</button>
      </form>
      <div class="quick-actions">
        <button data-template="解释这段内容：">解释</button>
        <button data-template="翻译成中文：">翻译</button>
        <button data-template="帮我总结：">总结</button>
        <button data-template="根据这段内容写代码：">写代码</button>
      </div>
    </section>
  `;

  const input = document.querySelector("#quickInput");
  document.querySelector("#quickForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    await desktop.openMain({ text });
    input.value = "";
  });
  document.querySelectorAll("[data-template]").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = `${button.dataset.template}${input.value}`;
      input.focus();
    });
  });
  desktop.onQuickFocus?.(() => input.focus());
  desktop.onQuickMode?.((nextMode) => {
    document.querySelector("#quickHint").textContent =
      nextMode === "screen" ? "截图问答快捷键已触发，可粘贴截图或描述屏幕内容" : "Enter 发送到主窗口";
    input.focus();
  });
}

function renderCaptureOverlay() {
  app.className = "capture-shell";
  app.innerHTML = `
    <div id="captureStage" class="capture-stage">
      <img id="captureImage" alt="" />
      <div class="capture-mask"></div>
      <div id="captureSelection" class="capture-selection hidden">
        <img id="captureSelectionImage" alt="" />
        <span id="captureSize" class="capture-size">0 x 0</span>
      </div>
      <div id="captureToolbar" class="capture-toolbar hidden">
        <button id="captureCancel" class="cancel" title="取消">×</button>
        <button id="captureConfirm" class="confirm" title="确认">✓</button>
      </div>
    </div>
  `;

  const stage = document.querySelector("#captureStage");
  const image = document.querySelector("#captureImage");
  const selectionImage = document.querySelector("#captureSelectionImage");
  const selectionNode = document.querySelector("#captureSelection");
  const sizeNode = document.querySelector("#captureSize");
  const toolbar = document.querySelector("#captureToolbar");
  let dragStart = null;
  let selection = null;

  desktop.onCaptureStart?.((payload) => {
    image.src = payload.dataUrl;
    selectionImage.src = payload.dataUrl;
  });
  desktop.getCapturePayload?.().then((payload) => {
    if (payload?.dataUrl) {
      image.src = payload.dataUrl;
      selectionImage.src = payload.dataUrl;
    }
  });

  stage.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".capture-toolbar")) return;
    dragStart = { x: event.clientX, y: event.clientY };
    selection = { x: event.clientX, y: event.clientY, width: 0, height: 0 };
    stage.setPointerCapture(event.pointerId);
    updateCaptureSelection(selection);
  });

  stage.addEventListener("pointermove", (event) => {
    if (!dragStart) return;
    selection = normalizeSelection(dragStart, { x: event.clientX, y: event.clientY });
    updateCaptureSelection(selection);
  });

  stage.addEventListener("pointerup", (event) => {
    if (!dragStart) return;
    stage.releasePointerCapture(event.pointerId);
    dragStart = null;
    if (!selection || selection.width < 8 || selection.height < 8) {
      selection = null;
      selectionNode.classList.add("hidden");
      toolbar.classList.add("hidden");
      return;
    }
    updateCaptureSelection(selection);
  });

  document.querySelector("#captureCancel").addEventListener("click", () => desktop.cancelCapture());
  document.querySelector("#captureConfirm").addEventListener("click", () => {
    if (selection) desktop.confirmCapture(selection);
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape") desktop.cancelCapture();
    if (event.key === "Enter" && selection) desktop.confirmCapture(selection);
  });

  function updateCaptureSelection(next) {
    selectionNode.classList.remove("hidden");
    selectionNode.style.left = `${next.x}px`;
    selectionNode.style.top = `${next.y}px`;
    selectionNode.style.width = `${next.width}px`;
    selectionNode.style.height = `${next.height}px`;
    selectionImage.style.width = `${window.innerWidth}px`;
    selectionImage.style.height = `${window.innerHeight}px`;
    selectionImage.style.transform = `translate(${-next.x}px, ${-next.y}px)`;
    sizeNode.textContent = `${Math.round(next.width)} x ${Math.round(next.height)}`;
    if (next.width >= 8 && next.height >= 8) {
      toolbar.classList.remove("hidden");
      const toolbarTop = Math.min(window.innerHeight - 62, next.y + next.height + 12);
      const toolbarLeft = Math.min(window.innerWidth - 160, Math.max(12, next.x + next.width - 150));
      toolbar.style.left = `${toolbarLeft}px`;
      toolbar.style.top = `${toolbarTop}px`;
    } else {
      toolbar.classList.add("hidden");
    }
  }
}

async function saveUrl() {
  const input = document.querySelector("#webAppUrlInput");
  const webAppUrl = input.value.trim();
  config = await desktop.saveConfig({ webAppUrl });
  desktop.notify({
    title: "AgentHub Desktop",
    body: "Web 主端地址已保存。",
  });
}

function handleTitlebarAction(action) {
  if (action === "quick") desktop.quickInput();
  if (action === "screen") desktop.screenQuestion();
  if (action === "copy") desktop.copyUrl();
}

function updateNavigationState(state = {}) {
  const back = document.querySelector('[data-nav="back"]');
  const forward = document.querySelector('[data-nav="forward"]');
  const maximize = document.querySelector('[data-window="maximize"]');
  if (back) back.disabled = !state.canGoBack;
  if (forward) forward.disabled = !state.canGoForward;
  if (maximize) maximize.textContent = state.maximized ? "❐" : "□";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function normalizeSelection(start, end) {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  return {
    x,
    y,
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y),
  };
}

boot();
