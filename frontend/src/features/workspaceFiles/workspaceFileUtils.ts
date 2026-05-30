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
  const segment = lastSegment(path) || current;
  const isIdLike = isUuid(segment) || isShortId(segment) || isUuid(current);
  if (!isIdLike) return normalizeKnownSegment(current);
  if (path.startsWith("artifacts/") && isUuid(segment)) {
    const childFile = node.children?.find((child) => child.type === "file");
    const title = stripExtension(childFile?.display_name ?? childFile?.name ?? "");
    return `产物：${title || "未命名产物"} · ${segment.slice(0, 8)}`;
  }
  if ((path.startsWith("uploads/legacy/") || path.startsWith("files/legacy/")) && isUuid(segment)) {
    const childFile = node.children?.find((child) => child.type === "file");
    const title = stripExtension(childFile?.display_name ?? childFile?.name ?? "");
    return `上传记录：${title || segment.slice(0, 8)}`;
  }
  if (isCurrentRoleSegment(path, "tasks")) return `任务运行 ${segment.slice(0, 8)}`;
  if (isCurrentRoleSegment(path, "agents")) return `Agent 工作区 ${segment.slice(0, 8)}`;
  if (isCurrentRoleSegment(path, "conversations")) return `会话：${segment.slice(0, 8)}`;
  if (path.includes("/conversations/") && isShortId(segment)) return `用户：${segment.slice(0, 8)}`;
  return `文件夹 ${segment.slice(0, 8)}`;
}

export function displayNodePath(node: WorkspaceFileNode) {
  const parts = node.path.split("/").filter(Boolean);
  if (!parts.length) return node.path;
  const readable = readablePathParts(parts.slice(0, -1), node);
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

function readablePathParts(parts: string[], node: WorkspaceFileNode) {
  const readable: string[] = [];
  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index];
    const previous = parts[index - 1];
    if (part === "uploads") readable.push("上传文件");
    else if (part === "artifacts") readable.push("产物文件");
    else if (part === "sandbox") readable.push("沙箱文件");
    else if (part === "exports") readable.push("导出文件");
    else if (part === "projects") readable.push("项目文件");
    else if (part === "files") readable.push("兼容文件");
    else if (part === "legacy") readable.push("兼容记录");
    else if (part === "conversations") readable.push("会话");
    else if (part === "agents") readable.push("Agent 输出");
    else if (part === "tasks") readable.push("任务输出");
    else if (isUuid(part) && previous === "artifacts") {
      readable.push(`产物：${stripExtension(node.display_name ?? node.name) || "未命名产物"} · ${part.slice(0, 8)}`);
    } else if (isUuid(part) && previous === "conversations") {
      readable.push(`会话 ${part.slice(0, 8)}`);
    } else if (isUuid(part) && previous === "agents") {
      readable.push(`Agent ${part.slice(0, 8)}`);
    } else if (isUuid(part) && previous === "tasks") {
      readable.push(`任务 ${part.slice(0, 8)}`);
    } else if (isShortId(part) && parts.includes("conversations")) {
      readable.push(`用户 ${part.slice(0, 8)}`);
    } else if (!isUuid(part)) {
      readable.push(part);
    }
  }
  return readable;
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

function isUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}

function lastSegment(path: string) {
  const parts = path.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

function isShortId(value: string) {
  return /^[0-9a-f]{8,12}$/i.test(value);
}

function isCurrentRoleSegment(path: string, role: string) {
  const parts = path.split("/").filter(Boolean);
  const roleIndex = parts.lastIndexOf(role);
  return roleIndex >= 0 && roleIndex === parts.length - 2;
}
