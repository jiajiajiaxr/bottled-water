import type { WorkspaceFileNode } from "../../types";

export function filterNodes(nodes: WorkspaceFileNode[], query: string, source: string): WorkspaceFileNode[] {
  const normalized = query.trim().toLowerCase();
  return nodes
    .map((node) => {
      const children = filterNodes(node.children ?? [], query, source);
      const sourceMatched = source === "all" || node.source === source;
      const textMatched =
        !normalized ||
        (node.display_name ?? node.name).toLowerCase().includes(normalized) ||
        node.path.toLowerCase().includes(normalized);
      if (node.type === "directory") {
        return children.length || (!normalized && source === "all") ? { ...node, children } : undefined;
      }
      return sourceMatched && textMatched ? node : undefined;
    })
    .filter(Boolean) as WorkspaceFileNode[];
}

export function walk(nodes: WorkspaceFileNode[], visit: (node: WorkspaceFileNode) => void) {
  for (const node of nodes) {
    visit(node);
    walk(node.children ?? [], visit);
  }
}

export function sourceLabel(source: string) {
  return {
    upload: "上传",
    artifact: "产物",
    sandbox: "沙箱",
    export: "导出",
    project: "项目",
    legacy: "兼容",
    workspace: "工作区",
    uploads: "上传",
    artifacts: "产物",
    files: "兼容",
    projects: "项目",
    logs: "日志",
    tools: "工具",
  }[source] ?? source;
}

export function displayNodeName(node: WorkspaceFileNode) {
  if (node.type !== "directory") return node.display_name ?? node.name;
  const current = node.display_name ?? node.name;
  const path = node.path || "";
  const uuid = uuidSegment(path) || (isUuid(current) ? current : "");
  if (!uuid) return normalizeKnownSegment(current);
  if (path.startsWith("artifacts/")) {
    const childFile = node.children?.find((child) => child.type === "file");
    const title = stripExtension(childFile?.display_name ?? childFile?.name ?? "");
    return `产物：${title || "未命名产物"} · ${uuid.slice(0, 8)}`;
  }
  if (path.includes("/conversations/")) return `会话：${uuid.slice(0, 8)}`;
  if (path.startsWith("uploads/legacy/") || path.startsWith("files/legacy/")) {
    const childFile = node.children?.find((child) => child.type === "file");
    const title = stripExtension(childFile?.display_name ?? childFile?.name ?? "");
    return `上传记录：${title || uuid.slice(0, 8)}`;
  }
  if (path.includes("/agents/")) return `Agent 工作区 ${uuid.slice(0, 8)}`;
  if (path.includes("/tasks/")) return `任务运行 ${uuid.slice(0, 8)}`;
  return `文件夹 ${uuid.slice(0, 8)}`;
}

export function displayNodePath(node: WorkspaceFileNode) {
  if (node.display_path) return node.display_path;
  const parts = node.path.split("/").filter(Boolean);
  if (!parts.length) return node.path;
  const readable = parts
    .slice(0, -1)
    .map((part, index) => readablePathPart(part, parts.slice(0, index + 1).join("/")))
    .filter(Boolean);
  return readable.join(" / ") || node.path;
}

export function formatSize(size: number) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size > 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${size} B`;
}

export function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function readablePathPart(part: string, path: string) {
  if (part === "uploads") return "上传文件";
  if (part === "artifacts") return "产物文件";
  if (part === "sandbox") return "沙箱文件";
  if (part === "exports") return "导出文件";
  if (part === "projects") return "项目文件";
  if (part === "files") return "兼容文件";
  if (part === "legacy") return "兼容记录";
  if (part === "conversations") return "会话";
  if (part === "agents") return "Agent 输出";
  if (part === "tasks") return "任务输出";
  if (!isUuid(part)) return part;
  if (path.startsWith("artifacts/")) return `产物 ${part.slice(0, 8)}`;
  if (path.includes("/conversations/")) return `会话 ${part.slice(0, 8)}`;
  if (path.includes("/agents/")) return `Agent ${part.slice(0, 8)}`;
  if (path.includes("/tasks/")) return `任务 ${part.slice(0, 8)}`;
  return part.slice(0, 8);
}

function normalizeKnownSegment(value: string) {
  return {
    legacy: "兼容记录",
    conversations: "会话",
    agents: "Agent 输出",
    tasks: "任务输出",
  }[value] ?? value;
}

function stripExtension(value: string) {
  return value.replace(/\.[^.]+$/, "");
}

function uuidSegment(path: string) {
  return path.split("/").find(isUuid);
}

function isUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
