const DEFAULT_API_BASE = "http://127.0.0.1:8000/api/v1";
const QUEUE_KEY = "agenthub_mobile_approval_queue";

export function getApiBase() {
  return localStorage.getItem("agenthub_mobile_api_base") || DEFAULT_API_BASE;
}

export function setApiBase(value) {
  localStorage.setItem("agenthub_mobile_api_base", value);
}

export async function loadDashboard() {
  const [health] = await Promise.allSettled([request("/health")]);
  return {
    online: health.status === "fulfilled",
    health: health.status === "fulfilled" ? health.value : undefined,
    conversations: fallbackConversations(),
    approvals: readApprovalQueue().length ? mergeQueuedApprovals() : fallbackApprovals(),
    artifacts: fallbackArtifacts(),
    progress: fallbackProgress(),
  };
}

export async function approveTask(id, decision) {
  const payload = {
    id,
    decision,
    decided_at: new Date().toISOString(),
  };

  try {
    await request(`/mobile/approvals/${encodeURIComponent(id)}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return { queued: false, payload };
  } catch {
    const queue = readApprovalQueue();
    queue.unshift(payload);
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue.slice(0, 50)));
    return { queued: true, payload };
  }
}

export function readApprovalQueue() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  } catch {
    return [];
  }
}

async function request(path, init = {}) {
  const token = localStorage.getItem("agenthub_token");
  const response = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  const payload = await response.json();
  return payload?.data ?? payload;
}

function mergeQueuedApprovals() {
  const queued = new Set(readApprovalQueue().map((item) => item.id));
  return fallbackApprovals().map((item) => ({
    ...item,
    status: queued.has(item.id) ? "queued" : item.status,
  }));
}

function fallbackConversations() {
  return [
    {
      id: "conv-roadmap",
      title: "课题研发总群",
      excerpt: "Team Leader 已拆出前端、后端、验证三个执行分支。",
      unread: 6,
      time: "09:42",
    },
    {
      id: "conv-deploy",
      title: "部署发布核验",
      excerpt: "Docker 健康检查通过，等待移动端审批。",
      unread: 2,
      time: "10:18",
    },
    {
      id: "conv-local",
      title: "本地资源联动",
      excerpt: "桌面端已纳管 3 个加密文件，准备同步到工作区。",
      unread: 1,
      time: "11:05",
    },
  ];
}

function fallbackApprovals() {
  return [
    {
      id: "approval-deploy",
      title: "允许发布预览环境",
      detail: "前后端联调通过，申请创建临时预览链接。",
      risk: "中",
      status: "pending",
    },
    {
      id: "approval-file",
      title: "允许读取本地加密资料",
      detail: "Backend Worker 需要读取桌面端纳管的需求文档摘要。",
      risk: "低",
      status: "pending",
    },
  ];
}

function fallbackArtifacts() {
  return [
    {
      id: "artifact-release",
      title: "AI 产品发布页",
      kind: "HTML",
      status: "可预览",
      url: "/release",
    },
    {
      id: "artifact-report",
      title: "课题阶段报告",
      kind: "PDF",
      status: "待核验",
      url: "",
    },
  ];
}

function fallbackProgress() {
  return [
    { label: "任务拆解", value: 100 },
    { label: "多 Agent 执行", value: 76 },
    { label: "成果核验", value: 58 },
    { label: "部署发布", value: 34 },
  ];
}
