const DEFAULT_API_BASE = inferApiBase();
const TOKEN_KEY = "agenthub_token";
const SNAPSHOT_KEY = "agenthub_mobile_snapshot";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
}

export function cachedDashboard() {
  try {
    return JSON.parse(localStorage.getItem(SNAPSHOT_KEY) || "null");
  } catch {
    return null;
  }
}

export async function login({ username, password, demo = false }) {
  const payload = demo
    ? await request("/auth/demo", { method: "POST", body: {}, auth: false })
    : await request("/auth/login", {
        method: "POST",
        body: { username, email: username, password },
        auth: false,
      });
  const token = payload?.access_token || payload?.token;
  if (!token) throw new Error("登录成功但后端没有返回令牌");
  localStorage.setItem(TOKEN_KEY, token);
  return payload.user;
}

export async function loadDashboard() {
  const [health, me, conversations, tasks] = await Promise.allSettled([
    request("/health", { auth: false }),
    getToken() ? request("/auth/me") : Promise.resolve(null),
    getToken() ? request("/conversations?include_workspace=true") : Promise.resolve(null),
    getToken() ? request("/tasks") : Promise.resolve([]),
  ]);

  const normalizedConversations = normalizeConversations(
    conversations.status === "fulfilled" ? conversations.value : null,
  );
  const conversationsWithMessages = getToken()
    ? await hydrateConversationMessages(normalizedConversations)
    : normalizedConversations;
  const normalizedTasks = normalizeTasks(tasks.status === "fulfilled" ? tasks.value : null);
  const artifacts = getToken() ? await hydrateArtifacts(conversationsWithMessages) : [];

  const snapshot = {
    online: health.status === "fulfilled",
    user: me.status === "fulfilled" ? me.value : null,
    conversations: conversationsWithMessages,
    tasks: normalizedTasks,
    artifacts,
    progress: normalizeProgress(normalizedTasks),
    syncedAt: new Date().toISOString(),
  };
  localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snapshot));
  return snapshot;
}

export async function loadConversationMessages(conversationId) {
  const payload = await request(`/conversations/${encodeURIComponent(conversationId)}/messages`);
  return normalizeMessages(payload);
}

export async function sendConversationMessage(conversationId, text) {
  const apiBase = DEFAULT_API_BASE;
  const token = getToken();
  const cleanText = String(text || "").trim();
  if (!cleanText) throw new Error("消息不能为空");
  const clientMessageId = `mobile-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20_000);
  let requestAccepted = false;

  let response;
  try {
    response = await fetch(`${apiBase}/conversations/${encodeURIComponent(conversationId)}/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        content_type: "text",
        content: { text: cleanText, attachments: [] },
        text: cleanText,
        client_message_id: clientMessageId,
      }),
      signal: controller.signal,
    });
  } catch (error) {
    window.clearTimeout(timeout);
    if (error?.name === "AbortError" && (await hasPersistedClientMessage(conversationId, clientMessageId))) return;
    throw error;
  }

  if (!response.ok) {
    window.clearTimeout(timeout);
    throw new Error(`${response.status} ${response.statusText || "消息发送失败"}`);
  }
  requestAccepted = true;

  if (!response.body) {
    window.clearTimeout(timeout);
    return;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop() || "";
      for (const record of parts) {
        const eventName = sseEventName(record);
        if (eventName === "system.session_error" || eventName === "generation:failed") {
          throw new Error("消息已发送，但 Agent 回复失败");
        }
        if (eventName === "message:new" || eventName === "message:updated" || eventName === "generation_finished") {
          await reader.cancel().catch(() => undefined);
          return;
        }
      }
    }
  } catch (error) {
    if (error?.name === "AbortError" && (requestAccepted || (await hasPersistedClientMessage(conversationId, clientMessageId)))) {
      return;
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function markConversationRead(conversationId) {
  try {
    await request(`/conversations/${encodeURIComponent(conversationId)}/read`, {
      method: "POST",
      body: {},
    });
  } catch {
    // Read markers should not block mobile browsing.
  }
}

export async function checkHealth() {
  return await request("/health", { auth: false });
}

async function request(path, init = {}) {
  const apiBase = DEFAULT_API_BASE;
  const token = getToken();
  let response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.auth === false ? {} : token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers || {}),
      },
      body: init.body && typeof init.body !== "string" ? JSON.stringify(init.body) : init.body,
    });
  } catch (error) {
    throw new Error("无法连接后端");
  }

  const text = await response.text();
  let payload = null;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text;
  }
  if (!response.ok) {
    const message = payload?.message || payload?.detail || response.statusText || "请求失败";
    throw new Error(`${response.status} ${message}`);
  }
  return payload?.data ?? payload;
}

async function hydrateConversationMessages(conversations) {
  if (!conversations.length) return [];
  const results = await Promise.allSettled(
    conversations.slice(0, 8).map((conversation) => loadConversationMessages(conversation.id)),
  );
  return conversations.map((conversation, index) => {
    const messages = results[index]?.status === "fulfilled" ? results[index].value : conversation.messages || [];
    const latest = messages[messages.length - 1];
    return {
      ...conversation,
      messages,
      excerpt: latest?.text || conversation.excerpt,
      time: latest?.time || conversation.time,
      messageCount: messages.length || conversation.messageCount,
    };
  });
}

async function hydrateArtifacts(conversations) {
  const messageArtifacts = conversations.flatMap(artifactsFromConversation);
  const results = await Promise.allSettled(
    conversations.slice(0, 8).map((conversation) =>
      request(`/conversations/${encodeURIComponent(conversation.id)}/artifacts`),
    ),
  );
  const endpointArtifacts = results.flatMap((result) =>
    result.status === "fulfilled" ? normalizeArtifacts(result.value) : [],
  );
  return dedupeArtifacts([...messageArtifacts, ...endpointArtifacts]);
}

function normalizeConversations(payload) {
  const source = Array.isArray(payload) ? payload : payload?.items || payload?.active;
  if (!Array.isArray(source) || !source.length) return [];
  return source.slice(0, 20).map((item) => ({
    id: item.id || item.conversation_id,
    title: item.title || item.name || "未命名会话",
    excerpt: item.last_message_preview || item.lastMessage || item.description || "暂无最新消息",
    unread: Number(item.unread_count || item.unread || 0),
    time: shortTime(item.last_message_at || item.updated_at || item.updatedAt || item.created_at),
    chatType: item.chat_type || item.type || "single",
    participantCount: Number(item.participant_count || item.participants?.length || 1),
    agentCount: Number(item.agent_count || 0),
    messageCount: Number(item.message_count || 0),
    messages: [],
  }));
}

function normalizeMessages(payload) {
  const source = Array.isArray(payload) ? payload : payload?.items;
  if (!Array.isArray(source)) return [];
  return source.map(normalizeMessage);
}

function normalizeMessage(item) {
  const raw = item?.rawContent && typeof item.rawContent === "object" ? item.rawContent : item?.content;
  const contentType = item?.content_type || item?.kind || "text";
  const card = normalizePreviewCard(raw, item);
  const text =
    typeof item?.content === "string"
      ? item.content
      : raw?.text || raw?.code || card?.title || item?.text || item?.prompt || "";
  return {
    id: item?.id || item?.message_id || item?.client_message_id || `message-${Date.now()}`,
    clientMessageId: item?.client_message_id || item?.clientMessageId || "",
    senderType: item?.sender_type || item?.role || "user",
    senderName: item?.sender_name || item?.author || (item?.sender_type === "agent" ? "Agent" : "用户"),
    text: String(text || ""),
    contentType,
    rawContent: raw && typeof raw === "object" ? raw : {},
    previewCard: contentType === "preview_card" ? card : null,
    status: item?.status || "sent",
    time: shortTime(item?.created_at || item?.createdAt),
  };
}

function normalizeTasks(payload) {
  const source = Array.isArray(payload) ? payload : payload?.items;
  if (!Array.isArray(source)) return [];
  return source.slice(0, 50).map((item) => ({
    id: item.id || item.task_id,
    title: item.title || "专项任务",
    description: item.description || "",
    status: item.status || "PENDING",
    progress: Number(item.progress ?? statusProgress(item.status)),
    updatedAt: item.updated_at || item.updatedAt || item.created_at,
  }));
}

function normalizeArtifacts(payload) {
  const source = Array.isArray(payload) ? payload : payload?.items;
  if (!Array.isArray(source)) return [];
  return source.slice(0, 20).map((item) => {
    const id = item.id || item.artifact_id;
    const format = item.format || item.media_type || item.type || "artifact";
    const preview = previewUrlForArtifact(id, {
      format,
      artifactType: item.artifact_type || item.type || item.kind,
      kind: item.kind,
      mediaType: item.media_type,
      filename: item.filename,
      previewUrl: item.preview_url || item.storage_url || item.export_url || "",
      exportUrl: item.export_url || "",
    });
    return {
      id,
      title: item.title || item.name || "未命名成果",
      kind: String(item.format || item.type || item.kind || "artifact").toUpperCase(),
      status: item.status || "可核验",
      url: preview.url,
      previewRequiresAuth: preview.requiresAuth,
      exportUrl: absoluteUrl(item.export_url || ""),
      format: String(format).toUpperCase(),
      conversationId: item.conversation_id || item.conversationId || "",
      source: "artifact",
    };
  });
}

function normalizePreviewCard(raw, item = {}) {
  const source = raw && typeof raw === "object" ? raw : {};
  const artifactId = source.artifact_id || source.artifactId || source.id || item.artifact_id || "";
  if (!artifactId && !source.preview_url && !source.export_url) return null;
  const format = source.format || source.media_type || source.artifact_type || "artifact";
  const preview = previewUrlForArtifact(artifactId, {
    format,
    artifactType: source.artifact_type || source.type || source.kind,
    kind: source.kind,
    mediaType: source.media_type,
    filename: source.filename,
    previewUrl: source.preview_url || "",
    exportUrl: source.export_url || "",
  });
  return {
    id: artifactId || item.id || `preview-${Date.now()}`,
    title: source.title || source.filename || item.content || "预览产物",
    kind: String(source.artifact_type || format || "artifact").toUpperCase(),
    status: source.status || "已生成，可预览",
    url: preview.url,
    previewRequiresAuth: preview.requiresAuth,
    exportUrl: absoluteUrl(source.export_url || ""),
    format: String(format || "artifact").toUpperCase(),
    filename: source.filename || "",
    conversationId: item.conversation_id || item.conversationId || "",
    messageId: item.id || item.message_id || "",
    source: "preview_card",
  };
}

function previewUrlForArtifact(
  artifactId,
  {
    format = "",
    artifactType = "",
    kind = "",
    mediaType = "",
    filename = "",
    previewUrl = "",
    exportUrl = "",
  } = {},
) {
  const normalized = `${format} ${artifactType} ${kind} ${mediaType} ${filename} ${previewUrl} ${exportUrl}`.toLowerCase();
  if (artifactId && shouldUsePdfPreview(normalized)) {
    return {
      url: absoluteUrl(`/api/v1/artifacts/${artifactId}/preview-pdf`),
      requiresAuth: true,
    };
  }
  return {
    url: absoluteUrl(previewUrl || ""),
    requiresAuth: false,
  };
}

function shouldUsePdfPreview(normalized) {
  if (normalized.includes("pdf")) return true;
  return [
    "docx",
    "word",
    "document",
    "xlsx",
    "excel",
    "spreadsheet",
    "pptx",
    "ppt",
    "presentation",
    "slides",
    "officedocument",
  ].some((keyword) => normalized.includes(keyword));
}

async function hasPersistedClientMessage(conversationId, clientMessageId) {
  try {
    const messages = await loadConversationMessages(conversationId);
    return messages.some((message) => message.clientMessageId === clientMessageId);
  } catch {
    return false;
  }
}

function sseEventName(record) {
  return String(record || "").match(/^event:\s*(.+)$/m)?.[1]?.trim() || "";
}

function artifactsFromConversation(conversation) {
  return (conversation.messages || [])
    .filter((message) => message.contentType === "preview_card" && message.previewCard)
    .map((message) => ({
      ...message.previewCard,
      conversationId: conversation.id,
      time: message.time,
    }));
}

function dedupeArtifacts(items) {
  const seen = new Map();
  for (const item of items) {
    if (!item?.id) continue;
    const previous = seen.get(item.id) || {};
    seen.set(item.id, { ...previous, ...item, url: item.url || previous.url, exportUrl: item.exportUrl || previous.exportUrl });
  }
  return Array.from(seen.values());
}

function normalizeProgress(tasks) {
  return tasks.slice(0, 6).map((item) => ({
    id: item.id,
    label: item.title,
    status: item.status,
    value: Number.isFinite(item.progress) ? item.progress : statusProgress(item.status),
  }));
}

function statusProgress(status) {
  const value = String(status || "").toUpperCase();
  if (["COMPLETED", "APPROVED", "DONE", "SUCCESS"].includes(value)) return 100;
  if (["RUNNING", "IN_PROGRESS", "PROCESSING"].includes(value)) return 66;
  if (["FAILED", "CANCELLED"].includes(value)) return 20;
  return 0;
}

function inferApiBase() {
  if (import.meta.env?.VITE_AGENTHUB_API_BASE) {
    return normalizeApiBase(import.meta.env.VITE_AGENTHUB_API_BASE);
  }
  if (isAndroidNative()) {
    return "http://10.0.2.2:8000/api/v1";
  }
  const host = window.location.hostname || "127.0.0.1";
  return `http://${host}:8000/api/v1`;
}

function normalizeApiBase(value) {
  return String(value || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");
}

function isAndroidNative() {
  const capacitorPlatform = window.Capacitor?.getPlatform?.();
  return capacitorPlatform === "android" || (window.location.protocol === "capacitor:" && /Android/i.test(navigator.userAgent));
}

function absoluteUrl(url) {
  if (!url) return "";
  if (/^https?:\/\//i.test(url)) return url;
  return `${DEFAULT_API_BASE.replace(/\/api\/v1$/, "")}${url.startsWith("/") ? url : `/${url}`}`;
}

function shortTime(value) {
  if (!value) return "--:--";
  try {
    return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "--:--";
  }
}
