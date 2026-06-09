import { approveTask, getApiBase, loadDashboard, readApprovalQueue, setApiBase } from "./api.js";
import "./styles.css";

const app = document.querySelector("#app");
let dashboard = {
  online: false,
  conversations: [],
  approvals: [],
  artifacts: [],
  progress: [],
};

function render() {
  app.innerHTML = `
    <main class="mobile-shell">
      <header class="mobile-header">
        <div>
          <span class="kicker">移动端轻量化便捷端口</span>
          <h1>AgentHub Mobile</h1>
        </div>
        <button id="refreshButton" class="icon-button" aria-label="刷新">↻</button>
      </header>

      <section class="status-strip ${dashboard.online ? "online" : "offline"}">
        <span></span>
        <strong>${dashboard.online ? "云端在线" : "离线可用"}</strong>
        <small>${readApprovalQueue().length} 条本地审批队列</small>
      </section>

      <section class="hero-panel">
        <p>外出时快速跟进课题研发进度，查看群聊，确认审批，核验成果。</p>
        <label class="api-field">
          <span>API</span>
          <input id="apiBaseInput" value="${escapeHtml(getApiBase())}" />
        </label>
      </section>

      <nav class="tabbar" aria-label="移动端模块">
        <button class="tab active" data-tab="chat">会话</button>
        <button class="tab" data-tab="approval">审批</button>
        <button class="tab" data-tab="artifact">成果</button>
        <button class="tab" data-tab="progress">进度</button>
      </nav>

      <section id="chatTab" class="tab-panel">${renderConversations()}</section>
      <section id="approvalTab" class="tab-panel hidden">${renderApprovals()}</section>
      <section id="artifactTab" class="tab-panel hidden">${renderArtifacts()}</section>
      <section id="progressTab" class="tab-panel hidden">${renderProgress()}</section>
    </main>
  `;

  wireEvents();
}

function renderConversations() {
  return dashboard.conversations
    .map(
      (item) => `
        <article class="conversation-card">
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <p>${escapeHtml(item.excerpt)}</p>
          </div>
          <aside>
            <span>${escapeHtml(item.time)}</span>
            <b>${item.unread}</b>
          </aside>
        </article>
      `,
    )
    .join("");
}

function renderApprovals() {
  return dashboard.approvals
    .map(
      (item) => `
        <article class="approval-card ${item.status}">
          <div class="card-head">
            <span>风险 ${escapeHtml(item.risk)}</span>
            <small>${item.status === "queued" ? "已进入离线队列" : "等待确认"}</small>
          </div>
          <h2>${escapeHtml(item.title)}</h2>
          <p>${escapeHtml(item.detail)}</p>
          <div class="button-row">
            <button class="secondary-action" data-approval="${item.id}" data-decision="reject">驳回</button>
            <button class="primary-action" data-approval="${item.id}" data-decision="approve">通过</button>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderArtifacts() {
  return dashboard.artifacts
    .map(
      (item) => `
        <article class="artifact-card">
          <div class="artifact-preview">
            <span>${escapeHtml(item.kind)}</span>
          </div>
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <p>${escapeHtml(item.status)}</p>
          </div>
          <button class="secondary-action" data-open="${escapeHtml(item.url)}">核验</button>
        </article>
      `,
    )
    .join("");
}

function renderProgress() {
  return dashboard.progress
    .map(
      (item) => `
        <article class="progress-card">
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <span>${item.value}%</span>
          </div>
          <meter min="0" max="100" value="${item.value}"></meter>
        </article>
      `,
    )
    .join("");
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.add("hidden"));
      document.querySelector(`#${button.dataset.tab}Tab`).classList.remove("hidden");
    });
  });

  document.querySelector("#refreshButton").addEventListener("click", hydrate);
  document.querySelector("#apiBaseInput").addEventListener("change", (event) => {
    setApiBase(event.target.value.trim());
    hydrate();
  });

  document.querySelectorAll("[data-approval]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      await approveTask(button.dataset.approval, button.dataset.decision);
      await hydrate();
    });
  });

  document.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => {
      const url = button.dataset.open;
      if (url) window.open(url, "_blank", "noopener,noreferrer");
    });
  });
}

async function hydrate() {
  dashboard = await loadDashboard();
  render();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  });
}

hydrate();
