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
