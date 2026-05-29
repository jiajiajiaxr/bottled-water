import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DeleteOutlined,
  DownloadOutlined,
  FileOutlined,
  FolderOpenOutlined,
  LinkOutlined,
  PlusCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Drawer,
  Empty,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Tree,
  Typography,
} from "antd";
import type { DataNode } from "antd/es/tree";
import { api } from "../../api";
import type { WorkspaceFileNode, WorkspaceFilePreview } from "../../types";

const { Text } = Typography;

type Props = {
  open: boolean;
  workspaceId?: string;
  onClose: () => void;
  onAttachReference: (snippet: string) => void;
};

export function WorkspaceFilesDrawer({
  open,
  workspaceId,
  onClose,
  onAttachReference,
}: Props) {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);
  const [nodes, setNodes] = useState<WorkspaceFileNode[]>([]);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<string>("all");
  const [preview, setPreview] = useState<{
    node: WorkspaceFileNode;
    payload: WorkspaceFilePreview;
  }>();

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const tree = await api.workspaceFileTree(workspaceId);
      setNodes(tree.items ?? tree.root.children ?? []);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (open) void load();
  }, [load, open]);

  const visibleNodes = useMemo(
    () => filterNodes(nodes, query, source),
    [nodes, query, source],
  );

  const sources = useMemo(() => {
    const values = new Set<string>();
    walk(nodes, (node) => {
      if (node.type === "file") values.add(node.source);
    });
    return [...values].sort();
  }, [nodes]);

  const handlePreview = async (node: WorkspaceFileNode) => {
    if (!workspaceId || node.type !== "file") return;
    const payload = await api.previewWorkspaceFile(workspaceId, node.id);
    setPreview({ node, payload });
  };

  const handleDownload = async (node: WorkspaceFileNode) => {
    if (!workspaceId) return;
    const file = await api.downloadWorkspaceFile(workspaceId, node.id);
    const href =
      file.previewUrl ??
      URL.createObjectURL(
        new Blob([file.previewText ?? ""], { type: file.contentType }),
      );
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = file.filename ?? node.name;
    anchor.click();
    if (!file.previewUrl) URL.revokeObjectURL(href);
  };

  const handleDelete = (node: WorkspaceFileNode) => {
    if (!workspaceId) return;
    Modal.confirm({
      title: "删除文件",
      content: `确认删除 ${node.name}？`,
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        await api.deleteWorkspaceFile(workspaceId, node.id);
        message.success("文件已删除");
        await load();
      },
    });
  };

  const attach = (node: WorkspaceFileNode) => {
    const fileId = node.id.startsWith("file:") ? ` file_id=${node.id.slice(5)}` : "";
    onAttachReference(`@file(${node.path}${fileId}) `);
    message.success("文件引用已加入输入框");
  };

  return (
    <>
      <Drawer
        title="工作区文件"
        open={open}
        onClose={onClose}
        width={760}
        className="workspace-files-drawer"
        extra={
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
            刷新
          </Button>
        }
      >
        <Space.Compact block className="workspace-file-toolbar">
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索文件名或路径"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Select
            value={source}
            onChange={setSource}
            style={{ width: 150 }}
            options={[
              { label: "全部来源", value: "all" },
              ...sources.map((item) => ({ label: sourceLabel(item), value: item })),
            ]}
          />
        </Space.Compact>
        {loading ? (
          <div className="workspace-file-loading">
            <Spin />
          </div>
        ) : visibleNodes.length ? (
          <Tree
            blockNode
            showIcon
            defaultExpandAll
            treeData={toTreeData(visibleNodes, {
              onPreview: handlePreview,
              onDownload: handleDownload,
              onDelete: handleDelete,
              onAttach: attach,
            })}
          />
        ) : (
          <Empty description="当前工作区暂无文件" />
        )}
      </Drawer>
      <Modal
        title={preview?.node.name}
        open={!!preview}
        onCancel={() => setPreview(undefined)}
        footer={null}
        width={820}
      >
        {preview && <WorkspaceFilePreviewView preview={preview.payload} />}
      </Modal>
    </>
  );
}

function toTreeData(
  nodes: WorkspaceFileNode[],
  actions: {
    onPreview: (node: WorkspaceFileNode) => void;
    onDownload: (node: WorkspaceFileNode) => void;
    onDelete: (node: WorkspaceFileNode) => void;
    onAttach: (node: WorkspaceFileNode) => void;
  },
): DataNode[] {
  return nodes.map((node) => ({
    key: node.id,
    icon: node.type === "directory" ? <FolderOpenOutlined /> : <FileOutlined />,
    title:
      node.type === "directory" ? (
        <Text strong>{node.name}</Text>
      ) : (
        <FileTreeTitle node={node} actions={actions} />
      ),
    children: node.children?.length ? toTreeData(node.children, actions) : undefined,
  }));
}

function FileTreeTitle({
  node,
  actions,
}: {
  node: WorkspaceFileNode;
  actions: {
    onPreview: (node: WorkspaceFileNode) => void;
    onDownload: (node: WorkspaceFileNode) => void;
    onDelete: (node: WorkspaceFileNode) => void;
    onAttach: (node: WorkspaceFileNode) => void;
  };
}) {
  return (
    <div className="workspace-file-row">
      <div className="workspace-file-meta">
        <Text strong ellipsis>
          {node.name}
        </Text>
        <Text type="secondary" ellipsis>
          {node.path}
        </Text>
      </div>
      <div className="workspace-file-actions">
        <Tag className="workspace-file-source">{sourceLabel(node.source)}</Tag>
        <Text type="secondary" className="workspace-file-size">
          {formatSize(node.size ?? 0)}
        </Text>
        <Text type="secondary" className="workspace-file-date">
          {formatDate(node.updated_at)}
        </Text>
        <Tooltip title="加入聊天上下文">
          <Button size="small" type="text" icon={<PlusCircleOutlined />} onClick={() => actions.onAttach(node)} />
        </Tooltip>
        <Tooltip title="复制路径">
          <Button
            size="small"
            type="text"
            icon={<LinkOutlined />}
            onClick={() => void navigator.clipboard.writeText(node.path)}
          />
        </Tooltip>
        <Button size="small" onClick={() => actions.onPreview(node)}>
          预览
        </Button>
        <Button size="small" icon={<DownloadOutlined />} onClick={() => actions.onDownload(node)} />
        <Button danger size="small" type="text" icon={<DeleteOutlined />} onClick={() => actions.onDelete(node)} />
      </div>
    </div>
  );
}

function WorkspaceFilePreviewView({ preview }: { preview: WorkspaceFilePreview }) {
  const text = preview.text ?? preview.preview_text ?? "";
  if ((preview.mode === "image" || preview.mode === "pdf") && preview.download_url) {
    return (
      <div>
        <Text type="secondary">该类型需要鉴权下载查看，点击下载按钮获取原文件。</Text>
      </div>
    );
  }
  if (preview.content_type?.includes("html")) {
    return <iframe title="workspace-file-preview" className="workspace-file-preview-frame" srcDoc={text} />;
  }
  return <pre className="workspace-file-preview-text">{text || "该文件暂不支持在线文本预览，可直接下载。"}</pre>;
}

function filterNodes(nodes: WorkspaceFileNode[], query: string, source: string): WorkspaceFileNode[] {
  const normalized = query.trim().toLowerCase();
  return nodes
    .map((node) => {
      const children = filterNodes(node.children ?? [], query, source);
      const sourceMatched = source === "all" || node.source === source;
      const textMatched =
        !normalized ||
        node.name.toLowerCase().includes(normalized) ||
        node.path.toLowerCase().includes(normalized);
      if (node.type === "directory") {
        return children.length ? { ...node, children } : undefined;
      }
      return sourceMatched && textMatched ? node : undefined;
    })
    .filter(Boolean) as WorkspaceFileNode[];
}

function walk(nodes: WorkspaceFileNode[], visit: (node: WorkspaceFileNode) => void) {
  for (const node of nodes) {
    visit(node);
    walk(node.children ?? [], visit);
  }
}

function sourceLabel(source: string) {
  return {
    upload: "上传",
    artifact: "产物",
    sandbox: "沙箱",
    export: "导出",
    project: "项目",
    legacy: "兼容",
  }[source] ?? source;
}

function formatSize(size: number) {
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
  if (size > 1024) return `${Math.ceil(size / 1024)} KB`;
  return `${size} B`;
}

function formatDate(value?: string) {
  if (!value) return "";
  return new Date(value).toLocaleString(undefined, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
