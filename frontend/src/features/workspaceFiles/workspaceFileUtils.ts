import type { WorkspaceFileNode } from "../../types";

export function filterNodes(
  nodes: WorkspaceFileNode[],
  query: string,
  source: string,
): WorkspaceFileNode[] {
  const normalized = query.trim().toLowerCase();
  return nodes
    .map((node) => {
      const children = filterNodes(node.children ?? [], query, source);
      const sourceMatched = source === "all" || node.source === source;
      const textMatched =
        !normalized ||
        (node.display_name ?? node.name).toLowerCase().includes(normalized) ||
        node.path.toLowerCase().includes(normalized) ||
        (node.display_path ?? "").toLowerCase().includes(normalized);
      if (node.type === "directory") {
        return children.length || (sourceMatched && textMatched)
          ? { ...node, children }
          : undefined;
      }
      return sourceMatched && textMatched ? node : undefined;
    })
    .filter(Boolean) as WorkspaceFileNode[];
}

export function insertDirectoryNode(
  nodes: WorkspaceFileNode[],
  directory: WorkspaceFileNode,
): WorkspaceFileNode[] {
  const parts = directory.path.split("/").filter(Boolean);
  if (!parts.length) return nodes;

  const cloneNode = (node: WorkspaceFileNode): WorkspaceFileNode => ({
    ...node,
    children: (node.children ?? []).map(cloneNode),
  });

  const next = nodes.map(cloneNode);
  let level = next;
  let currentPath = "";

  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index];
    currentPath = currentPath ? `${currentPath}/${part}` : part;
    let found = level.find((item) => item.path === currentPath && item.type === "directory");

    if (!found) {
      found =
        index === parts.length - 1
          ? {
              ...directory,
              children: directory.children ?? [],
            }
          : {
              id: `dir:${encodeURIComponent(currentPath)}`,
              name: part,
              display_name: part,
              type: "directory",
              path: currentPath,
              source: currentPath.split("/")[0] || directory.source || "workspace",
              children: [],
            };
      level.push(found);
    } else if (index === parts.length - 1) {
      found.name = directory.name;
      found.display_name = directory.display_name ?? directory.name;
      found.source = directory.source || found.source;
    }

    level = found.children ?? (found.children = []);
  }

  return next;
}

export function walk(nodes: WorkspaceFileNode[], visit: (node: WorkspaceFileNode) => void) {
  for (const node of nodes) {
    visit(node);
    walk(node.children ?? [], visit);
  }
}

export function sourceLabel(source: string) {
  return (
    {
      upload: "上传",
      uploads: "上传",
      artifact: "产物",
      artifacts: "产物",
      sandbox: "沙箱",
      export: "导出",
      exports: "导出",
      project: "项目",
      projects: "项目",
      legacy: "兼容",
      files: "兼容",
      workspace: "工作区",
      logs: "日志",
      tools: "工具",
    }[source] ?? source
  );
}

export function displayNodeName(node: WorkspaceFileNode) {
  return node.display_name ?? node.name;
}

export function displayNodePath(node: WorkspaceFileNode) {
  if (node.display_path) return node.display_path;
  const parts = node.path.split("/").filter(Boolean);
  if (!parts.length) return node.path;
  return readablePathParts(parts.slice(0, -1)).join(" / ") || node.path;
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

function readablePathParts(parts: string[]) {
  return parts
    .map((part) => {
      if (part === "uploads") return "上传文件";
      if (part === "artifacts") return "产物文件";
      if (part === "sandbox") return "沙箱文件";
      if (part === "exports") return "导出文件";
      if (part === "projects") return "项目文件";
      if (part === "files") return "兼容文件";
      if (part === "legacy") return "历史文件";
      if (part === "conversations") return "按会话归档";
      if (part === "agents") return "Agent 输出";
      if (part === "tasks") return "任务输出";
      if (isUuid(part)) return `${part.slice(0, 8)}`;
      return part;
    })
    .filter(Boolean);
}

function isUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
