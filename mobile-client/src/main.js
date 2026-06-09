import {
  cachedDashboard,
  checkHealth,
  getToken,
  loadConversationMessages,
  loadDashboard,
  login,
  logout,
  markConversationRead,
  sendConversationMessage,
} from "./api.js";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import "./styles.css";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

const app = document.querySelector("#app");

let activeTab = "chat";
let selectedConversationId = "";
let loading = false;
let sending = false;
let statusMessage = "";
let statusKind = "info";
let dashboard = emptyDashboard();
let activePreview = null;
let activePreviewSequence = 0;

function emptyDashboard() {
  return {
    online: false,
    user: null,
    conversations: [],
    artifacts: [],
    progress: [],
    tasks: [],
  };
}

function render() {
  app.innerHTML = `
    <main class="mobile-shell">
      <header class="mobile-header">
        <div class="brand-block">
          <span class="brand-mark">A</span>
          <div>
            <span class="kicker">移动端轻量化便捷端口</span>
            <h1>AgentHub Mobile</h1>
          </div>
        </div>
        <button id="refreshButton" class="icon-button" aria-label="刷新" ${loading ? "disabled" : ""}>↻</button>
      </header>

      ${renderStatus()}
      ${getToken() ? renderWorkspace() : renderLogin()}
      ${activePreview ? renderPdfPreviewSheet(activePreview) : ""}
    </main>
  `;
  wireEvents();
}

function renderStatus() {
  return `
    <section class="status-strip ${dashboard.online ? "online" : "offline"}">
      <span></span>
      <strong>${dashboard.online ? "云端在线" : "等待连接"}</strong>
      <small>${getToken() ? "已登录" : "未登录"}</small>
    </section>
    ${statusMessage ? `<div class="toast ${statusKind}">${escapeHtml(statusMessage)}</div>` : ""}
  `;
}

function renderLogin() {
  return `
    <section class="login-panel">
      <p class="hero-label">外出碎片化办公</p>
      <h2>查看会话、核验成果、跟进进度</h2>

      <div class="login-grid">
        <input id="usernameInput" placeholder="账号" value="demo" />
        <input id="passwordInput" placeholder="密码" type="password" value="agenthub" />
      </div>
      <div class="button-row">
        <button id="demoLoginButton" class="secondary-action" ${loading ? "disabled" : ""}>演示登录</button>
        <button id="loginButton" class="primary-action" ${loading ? "disabled" : ""}>${loading ? "登录中..." : "登录同步"}</button>
      </div>
    </section>

    <section class="capability-strip">
      <div><strong>会话</strong><span>在线查看全域协同</span></div>
      <div><strong>成果</strong><span>快速核验成品预览</span></div>
      <div><strong>进度</strong><span>跟进课题研发状态</span></div>
    </section>
  `;
}

function renderWorkspace() {
  return `
    <section class="mobile-hero">
      <p class="hero-label">当前同步账号</p>
      <h2>${escapeHtml(displayName())}</h2>
      <p>实时查看协同会话、成果预览和课题研发进度。</p>
      <div class="mobile-metrics">
        <button data-tab-jump="chat"><strong>${dashboard.conversations.length}</strong><span>会话</span></button>
        <button data-tab-jump="artifact"><strong>${realArtifactCount()}</strong><span>成果</span></button>
        <button data-tab-jump="progress"><strong>${dashboard.tasks.length}</strong><span>任务</span></button>
      </div>
    </section>

    <nav class="tabbar" aria-label="移动端模块">
      <button class="tab ${activeTab === "chat" ? "active" : ""}" data-tab="chat">会话</button>
      <button class="tab ${activeTab === "artifact" ? "active" : ""}" data-tab="artifact">成果</button>
      <button class="tab ${activeTab === "progress" ? "active" : ""}" data-tab="progress">进度</button>
    </nav>

    <section class="tab-panel">
      ${activeTab === "chat" ? renderChat() : ""}
      ${activeTab === "artifact" ? renderArtifacts() : ""}
      ${activeTab === "progress" ? renderProgress() : ""}
    </section>

    <button id="logoutButton" class="logout-button">退出登录</button>
  `;
}

function renderChat() {
  const selected = selectedConversation();
  if (selected) return renderConversationDetail(selected);
  const conversations = dashboard.conversations || [];
  return `
    <article class="section-card compact">
      <div class="card-head">
        <span>协同会话</span>
        <small>${dashboard.syncedAt ? new Date(dashboard.syncedAt).toLocaleTimeString() : "未同步"}</small>
      </div>
    </article>
    ${
      conversations.length
        ? conversations
            .map(
              (item) => `
          <button class="conversation-card" data-open-conversation="${escapeHtml(item.id)}">
            <div>
              <strong>${escapeHtml(item.title)}</strong>
              <p>${escapeHtml(item.excerpt)}</p>
              <small>${item.chatType === "group" ? "群聊" : "单聊"} · ${item.messageCount || item.messages?.length || 0} 条消息</small>
            </div>
            <aside>
              <span>${escapeHtml(item.time)}</span>
              ${item.unread ? `<b>${item.unread}</b>` : "<i>已读</i>"}
            </aside>
          </button>
        `,
            )
            .join("")
        : `<article class="section-card empty-state"><p>当前账号暂无可同步会话。请确认移动端登录账号与 Web 端一致，或在 Web 端创建会话后刷新。</p></article>`
    }
  `;
}

function renderConversationDetail(conversation) {
  const messages = conversation.messages || [];
  return `
    <article class="chat-room">
      <div class="chat-room-head">
        <button class="back-button" data-back-conversations>‹</button>
        <div>
          <strong>${escapeHtml(conversation.title)}</strong>
          <span>${conversation.chatType === "group" ? "群聊" : "单聊"} · ${conversation.participantCount || 1} 人</span>
        </div>
        <button id="refreshConversationButton" class="icon-button small" aria-label="刷新会话">↻</button>
      </div>
      <div class="message-thread">
        ${
          messages.length
            ? messages.map((message) => renderMessage(message)).join("")
            : `<div class="empty-chat">暂无消息。</div>`
        }
      </div>
      <form class="composer" id="composerForm">
        <textarea id="messageInput" rows="1" placeholder="输入消息" ${sending ? "disabled" : ""}></textarea>
        <button class="primary-action send-button" type="submit" ${sending ? "disabled" : ""}>${sending ? "发送中" : "发送"}</button>
      </form>
    </article>
  `;
}

function renderMessage(message) {
  if (message.contentType === "preview_card" && message.previewCard) {
    return renderPreviewCard(message.previewCard, { inline: true, senderName: message.senderName, time: message.time });
  }
  const outgoing = message.senderType === "user";
  return `
    <article class="message-bubble ${outgoing ? "outgoing" : "incoming"}">
      <div class="message-avatar">${escapeHtml(initials(message.senderName || message.senderType))}</div>
      <div class="message-body">
        <div>
          <strong>${escapeHtml(message.senderName || "未知成员")}</strong>
          <span>${escapeHtml(message.time || "")}</span>
        </div>
        <p>${escapeHtml(message.text || `[${message.contentType || "消息"}]`)}</p>
      </div>
    </article>
  `;
}

function renderArtifacts() {
  const artifacts = dashboard.artifacts || [];
  return `
    <article class="section-card compact">
      <div class="card-head">
        <span>成果核验</span>
        <small>${realArtifactCount()} 个成果</small>
      </div>
    </article>
    ${
      artifacts.length
        ? artifacts.map((item) => renderPreviewCard(item)).join("")
        : `<article class="section-card empty-state"><p>当前账号暂无真实成果卡片。Web 端生成预览产物后，这里会同步显示可点击核验的卡片。</p></article>`
    }
  `;
}

function renderPreviewCard(item, options = {}) {
  const inline = Boolean(options.inline);
  const title = item.title || item.filename || "预览产物";
  const kind = item.format || item.kind || "ART";
  return `
    <article class="${inline ? "preview-card inline-preview" : "preview-card"}">
      <div class="preview-card-head">
        <div class="preview-icon">${escapeHtml(String(kind).slice(0, 4))}</div>
        <div>
          <span>${inline ? escapeHtml(options.senderName || "Agent") : "预览产物"}</span>
          <strong>${escapeHtml(title)}</strong>
          <small>${escapeHtml(item.status || "已生成，可预览")}${options.time ? ` · ${escapeHtml(options.time)}` : ""}</small>
        </div>
      </div>
      <div class="preview-actions">
        <button class="primary-action" data-preview="${escapeHtml(item.url || "")}" data-preview-auth="${item.previewRequiresAuth ? "true" : "false"}" ${item.url ? "" : "disabled"}>预览</button>
        <button class="secondary-action" data-download="${escapeHtml(item.exportUrl || "")}" ${item.exportUrl ? "" : "disabled"}>下载</button>
      </div>
    </article>
  `;
}

function renderPdfPreviewSheet(preview) {
  const pages = Array.isArray(preview.pages) ? preview.pages : [];
  return `
    <section class="pdf-preview-sheet" role="dialog" aria-modal="true" aria-label="PDF 预览">
      <div class="pdf-preview-head">
        <div>
          <span>${preview.loading ? "正在生成预览" : "真实 PDF 预览"}</span>
          <strong>${escapeHtml(preview.title || "预览产物")}</strong>
        </div>
        <button class="icon-button small" type="button" data-close-preview aria-label="关闭预览">×</button>
      </div>
      <div class="pdf-preview-pages" aria-live="polite">
        ${
          preview.error
            ? `<div class="pdf-preview-state error">${escapeHtml(preview.error)}</div>`
            : preview.loading
              ? `<div class="pdf-preview-state">正在渲染 PDF 页面...</div>`
              : pages.length
                ? pages
                    .map(
                      (page) => `
                        <figure class="pdf-page">
                          <img src="${escapeHtml(page.url)}" alt="第 ${page.number} 页" />
                          <figcaption>${page.number} / ${pages.length}</figcaption>
                        </figure>
                      `,
                    )
                    .join("")
                : `<div class="pdf-preview-state">暂无可预览页面</div>`
        }
      </div>
      <div class="pdf-preview-actions">
        <button class="secondary-action" type="button" data-close-preview>关闭</button>
        <button class="primary-action" type="button" data-open-preview-window="${escapeHtml(preview.url)}">新窗口打开</button>
      </div>
    </section>
  `;
}

function renderProgress() {
  if (!dashboard.progress.length) {
    return `
      <article class="section-card empty-state">
        <div class="card-head">
          <span>研发进度</span>
          <small>0 个任务</small>
        </div>
        <p>当前后端没有同步到真实任务。Web 端创建任务后，这里会显示任务状态和进度。</p>
      </article>
    `;
  }
  return `
    <article class="section-card">
      <div class="card-head">
        <span>研发进度</span>
        <small>${dashboard.tasks.length} 个任务</small>
      </div>
      <div class="timeline">
        ${dashboard.progress
          .map(
            (item) => `
              <div class="timeline-item">
                <div>
                  <strong>${escapeHtml(item.label)}</strong>
                  <span>${item.value}%</span>
                </div>
                <meter min="0" max="100" value="${item.value}"></meter>
                <small>${escapeHtml(item.status)}</small>
              </div>
            `,
          )
          .join("")}
      </div>
    </article>
  `;
}

function wireEvents() {
  document.querySelector("#refreshButton")?.addEventListener("click", hydrate);
  document.querySelector("#loginButton")?.addEventListener("click", () => loginFromForm(false));
  document.querySelector("#demoLoginButton")?.addEventListener("click", () => loginFromForm(true));
  document.querySelector("#logoutButton")?.addEventListener("click", () => {
    logout();
    dashboard = emptyDashboard();
    selectedConversationId = "";
    setStatus("已退出登录", "info");
    render();
  });

  document.querySelectorAll("[data-tab], [data-tab-jump]").forEach((button) => {
    button.addEventListener("click", () => {
      activeTab = button.dataset.tab || button.dataset.tabJump;
      selectedConversationId = "";
      render();
    });
  });

  document.querySelectorAll("[data-open-conversation]").forEach((button) => {
    button.addEventListener("click", async () => {
      selectedConversationId = button.dataset.openConversation;
      render();
      await refreshSelectedConversation();
    });
  });

  document.querySelector("[data-back-conversations]")?.addEventListener("click", () => {
    selectedConversationId = "";
    render();
  });
  document.querySelector("#refreshConversationButton")?.addEventListener("click", refreshSelectedConversation);
  document.querySelector("#composerForm")?.addEventListener("submit", sendSelectedConversationMessage);
  document.querySelectorAll("[data-close-preview]").forEach((button) => {
    button.addEventListener("click", () => closeActivePreview());
  });
  document.querySelector("[data-open-preview-window]")?.addEventListener("click", () => {
    const url = document.querySelector("[data-open-preview-window]")?.dataset.openPreviewWindow;
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  });

  document.querySelectorAll("[data-preview]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!button.dataset.preview) return;
      if (button.dataset.previewAuth === "true") {
        await openAuthenticatedFile(button.dataset.preview, { inline: true, title: previewTitleFromButton(button) });
      } else {
        window.open(button.dataset.preview, "_blank", "noopener,noreferrer");
      }
    });
  });
  document.querySelectorAll("[data-download]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.dataset.download) await openAuthenticatedFile(button.dataset.download);
    });
  });
}

async function loginFromForm(demo) {
  loading = true;
  setStatus("正在连接后端...", "info", false);
  render();
  try {
    const username = document.querySelector("#usernameInput")?.value.trim() || "demo";
    const password = document.querySelector("#passwordInput")?.value || "agenthub";
    await checkHealth();
    await login({ username, password, demo });
    await hydrate("登录成功，已同步最新数据");
  } catch (error) {
    loading = false;
    setStatus(error.message || "登录失败", "error");
    render();
  }
}

async function hydrate(successMessage = "同步完成") {
  if (!getToken()) {
    render();
    return;
  }
  loading = true;
  setStatus("正在同步...", "info", false);
  render();
  try {
    dashboard = await loadDashboard();
    loading = false;
    setStatus(successMessage, "success");
  } catch (error) {
    dashboard = cachedDashboard() || dashboard;
    loading = false;
    setStatus(error.message || "同步失败，已显示缓存", "error");
  }
  render();
}

async function sendSelectedConversationMessage(event) {
  event.preventDefault();
  const conversation = selectedConversation();
  const input = document.querySelector("#messageInput");
  const text = input?.value?.trim() || "";
  if (!conversation || !text || sending) return;
  sending = true;
  setStatus("正在发送消息并等待 Agent 回复...", "info", false);
  render();
  try {
    await sendConversationMessage(conversation.id, text);
    await refreshSelectedConversation({ silent: true });
    sending = false;
    setStatus("消息已发送并同步", "success");
    scheduleConversationRefresh(conversation.id);
  } catch (error) {
    await refreshSelectedConversation({ silent: true });
    sending = false;
    setStatus(error.message || "消息发送失败", "error");
  }
  render();
}

function closeActivePreview() {
  activePreviewSequence += 1;
  clearActivePreviewUrls();
  if (activePreview?.url?.startsWith("blob:")) URL.revokeObjectURL(activePreview.url);
  activePreview = null;
  render();
}

function scheduleConversationRefresh(conversationId) {
  window.setTimeout(async () => {
    if (selectedConversationId === conversationId) {
      await refreshSelectedConversation();
    }
  }, 2500);
}

async function refreshSelectedConversation() {
  const conversation = selectedConversation();
  if (!conversation) return;
  try {
    const messages = await loadConversationMessages(conversation.id);
    dashboard = {
      ...dashboard,
      conversations: dashboard.conversations.map((item) =>
        item.id === conversation.id
          ? {
              ...item,
              messages,
              unread: 0,
              messageCount: messages.length,
              excerpt: messages[messages.length - 1]?.text || item.excerpt,
              time: messages[messages.length - 1]?.time || item.time,
            }
          : item,
      ),
    };
    await markConversationRead(conversation.id);
    dashboard = {
      ...dashboard,
      artifacts: mergeArtifacts(
        dashboard.artifacts,
        messages
          .filter((message) => message.contentType === "preview_card" && message.previewCard)
          .map((message) => ({ ...message.previewCard, conversationId: conversation.id, time: message.time })),
      ),
    };
  } catch (error) {
    setStatus(error.message || "会话同步失败", "error");
  }
  render();
}

function setStatus(message, kind = "info", autoRender = true) {
  statusMessage = message;
  statusKind = kind;
  if (autoRender) render();
}

function selectedConversation() {
  return dashboard.conversations.find((item) => item.id === selectedConversationId);
}

function displayName() {
  return dashboard.user?.display_name || dashboard.user?.username || dashboard.user?.email || "已登录";
}

function realArtifactCount() {
  return dashboard.artifacts.length;
}

function mergeArtifacts(current = [], incoming = []) {
  const seen = new Map();
  for (const item of [...current, ...incoming]) {
    if (item?.id) seen.set(item.id, { ...(seen.get(item.id) || {}), ...item });
  }
  return Array.from(seen.values());
}

async function openAuthenticatedFile(url, options = {}) {
  const title = options.title || "预览产物";
  try {
    if (options.inline) {
      await openPdfPreview(url, title);
      return;
    }
    const response = await fetch(url, {
      headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    window.open(objectUrl, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch (error) {
    setStatus(error.message || "下载失败", "error");
  }
}

async function openPdfPreview(url, title) {
  const sequence = ++activePreviewSequence;
  clearActivePreviewUrls();
  activePreview = { url, title, loading: true, pages: [] };
  render();
  try {
    const response = await fetch(url, {
      headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText || "PDF 获取失败"}`);
    const bytes = await response.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: bytes }).promise;
    const pages = [];
    const maxPages = Math.min(pdf.numPages, 20);
    for (let pageNumber = 1; pageNumber <= maxPages; pageNumber += 1) {
      if (sequence !== activePreviewSequence) return;
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale: pdfPreviewScale(page) });
      const canvas = document.createElement("canvas");
      const context = canvas.getContext("2d");
      canvas.width = Math.ceil(viewport.width);
      canvas.height = Math.ceil(viewport.height);
      await page.render({ canvasContext: context, viewport }).promise;
      pages.push({ number: pageNumber, url: canvas.toDataURL("image/png") });
      page.cleanup?.();
    }
    await pdf.destroy?.();
    if (sequence !== activePreviewSequence) return;
    activePreview = { url, title, loading: false, pages };
    render();
  } catch (error) {
    if (sequence !== activePreviewSequence) return;
    activePreview = {
      url,
      title,
      loading: false,
      pages: [],
      error: error.message || "PDF 预览生成失败",
    };
    render();
  }
}

function pdfPreviewScale(page) {
  const viewport = page.getViewport({ scale: 1 });
  const targetWidth = Math.min(window.innerWidth - 32, 960);
  return Math.max(1, Math.min(2.2, targetWidth / viewport.width));
}

function clearActivePreviewUrls() {
  if (!activePreview?.pages) return;
  for (const page of activePreview.pages) {
    if (page.url?.startsWith("blob:")) URL.revokeObjectURL(page.url);
  }
}

function previewTitleFromButton(button) {
  return button.closest(".preview-card")?.querySelector(".preview-card-head strong")?.textContent?.trim() || "预览产物";
}

function initials(value) {
  const text = String(value || "A").trim();
  return text.slice(0, 1).toUpperCase();
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
