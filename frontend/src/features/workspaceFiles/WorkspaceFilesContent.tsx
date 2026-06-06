import { useCallback, useEffect, useMemo, useState } from "react";
import type { Key } from "react";
import { FileOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { App as AntApp, Empty, Input, Modal, Select, Space, Spin, Tree, Upload } from "antd";
import type { UploadProps } from "antd";
import type { DataNode } from "antd/es/tree";
import { api } from "../../api";
import type { WorkspaceFileNode } from "../../types";
import { FileTreeRow } from "./FileTreeRow";
import type { FileRowActions } from "./FileTreeRow";
import { WorkspaceFileToolbar } from "./WorkspaceFileToolbar";
import { WorkspaceFileMap } from "./WorkspaceFileMap";
import type { PreviewState } from "./WorkspaceFilePreviewView";
import { WorkspaceFilePreviewView } from "./WorkspaceFilePreviewView";
import { filterNodes, sourceLabel, walk } from "./workspaceFileUtils";

type Props = {
  workspaceId?: string;
  activeConversationId?: string;
  onBack: () => void;
  onAttachReference: (snippet: string) => void;
};

export function WorkspaceFilesContent({
  workspaceId,
  activeConversationId,
  onBack,
  onAttachReference,
}: Props) {
  const { message } = AntApp.useApp();
  const [loading, setLoading] = useState(false);
  const [nodes, setNodes] = useState<WorkspaceFileNode[]>([]);
  const [stats, setStats] = useState<{ file_count: number; total_size: number }>();
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("all");
  const [preview, setPreview] = useState<PreviewState>();
  const [checkedKeys, setCheckedKeys] = useState<string[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const previewObjectUrl = preview?.objectUrl;

  const closePreview = useCallback(() => {
    if (preview?.objectUrl) URL.revokeObjectURL(preview.objectUrl);
    setPreview(undefined);
  }, [preview]);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    setLoading(true);
    try {
      const tree = await api.workspaceFileTree(workspaceId);
      setNodes(tree.items ?? tree.root.children ?? []);
      setStats(tree.stats);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!workspaceId) {
      setExpandedKeys([]);
      return;
    }
    const stored = window.localStorage.getItem(expandedStorageKey(workspaceId));
    if (!stored) {
      setExpandedKeys([]);
      return;
    }
    try {
      const parsed = JSON.parse(stored);
      setExpandedKeys(Array.isArray(parsed) ? parsed.map(String) : []);
    } catch {
      setExpandedKeys([]);
    }
  }, [workspaceId]);

  useEffect(
    () => () => {
      if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    },
    [previewObjectUrl],
  );

  const visibleNodes = useMemo(() => filterNodes(nodes, query, source), [nodes, query, source]);

  const sources = useMemo(() => {
    const values = new Set<string>();
    walk(nodes, (node) => {
      if (node.type === "file") values.add(node.source);
    });
    return [...values].sort();
  }, [nodes]);

  const directories = useMemo(() => {
    const items: Array<{ label: string; value: string }> = [
      { label: "文件区", value: "files" },
    ];
    walk(nodes, (node) => {
      if (node.type === "directory" && node.path) {
        items.push({
          label: `${node.display_name ?? node.name} · ${node.path}`,
          value: node.path,
        });
      }
    });
    return items;
  }, [nodes]);

  const handlePreview = async (node: WorkspaceFileNode) => {
    if (!workspaceId || node.type !== "file") return;
    if (preview?.objectUrl) URL.revokeObjectURL(preview.objectUrl);
    if (isOfficeFileNode(node)) {
      setPreview({
        node,
        payload: { mode: "loading", filename: node.display_name ?? node.name },
        loading: true,
        loadingText: "正在生成 PDF 预览...",
      });
    }
    try {
      const rawPayload = await api.previewWorkspaceFile(workspaceId, node.id);
      let payload = { ...rawPayload, mode: normalizePreviewMode(rawPayload, node) };
      let objectUrl: string | undefined;
      let error: string | undefined;

      if (payload.mode === "pdf" || payload.mode === "image") {
        try {
          const file =
            payload.preview_pdf_url || payload.preview_download_url
              ? await api.downloadWorkspaceFilePreviewPdf(workspaceId, node.id)
              : await api.downloadWorkspaceFile(workspaceId, node.id);
          objectUrl = file.previewUrl;
          if (!objectUrl) {
            error =
              payload.mode === "pdf"
                ? "PDF 文件下载失败，无法在线预览。"
                : "图片文件下载失败，无法在线预览。";
          }
        } catch (downloadError) {
          const detail = downloadError instanceof Error ? downloadError.message : "下载接口异常";
          error =
            payload.mode === "pdf"
              ? `PDF 文件下载失败：${detail}`
              : `图片文件下载失败：${detail}`;
        }
      }

      if (payload.mode === "html" && !previewText(payload)) {
        try {
          const file = await api.downloadWorkspaceFile(workspaceId, node.id);
          if (file.previewText) {
            payload = {
              ...payload,
              text: file.previewText,
              preview_text: file.previewText,
              content_type: file.contentType,
              filename: file.filename ?? payload.filename,
            };
          } else if (file.previewUrl) {
            objectUrl = file.previewUrl;
          }
        } catch (downloadError) {
          const detail = downloadError instanceof Error ? downloadError.message : "下载接口异常";
          error = `HTML 文件下载失败：${detail}`;
        }
      }

      setPreview({ node, payload, objectUrl, error });
    } catch (error) {
      const detail = error instanceof Error ? error.message : "预览失败";
      message.error(detail);
      setPreview({
        node,
        payload: { mode: "binary", filename: node.display_name ?? node.name },
        error: detail,
      });
    }
  };

  const handleDownload = async (node: WorkspaceFileNode) => {
    if (!workspaceId || node.type !== "file") return;
    const file = await api.downloadWorkspaceFile(workspaceId, node.id);
    const href =
      file.previewUrl ?? URL.createObjectURL(new Blob([file.previewText ?? ""], { type: file.contentType }));
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = file.filename ?? node.display_name ?? node.name;
    anchor.click();
    if (!file.previewUrl) URL.revokeObjectURL(href);
  };

  const handleUpload: UploadProps["beforeUpload"] = async (file) => {
    if (!workspaceId) {
      message.warning("请先选择一个工作区");
      return Upload.LIST_IGNORE;
    }
    try {
      const uploaded = await api.uploadFile(
        file,
        activeConversationId,
        "attachment",
        workspaceId,
      );
      message.success(`${uploaded.original_filename || file.name} 已上传到工作区文件`);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : "文件上传失败");
    }
    return Upload.LIST_IGNORE;
  };

  const handleRename = (node: WorkspaceFileNode) => {
    if (!workspaceId) return;
    let nextName = node.display_name ?? node.name;
    Modal.confirm({
      title: "重命名",
      content: (
        <Input
          defaultValue={nextName}
          autoFocus
          onChange={(event) => {
            nextName = event.target.value;
          }}
        />
      ),
      okText: "保存",
      onOk: async () => {
        await api.renameWorkspaceFile(workspaceId, node.id, nextName);
        message.success("已重命名");
        await load();
      },
    });
  };

  const handleDelete = (node: WorkspaceFileNode) => {
    if (!workspaceId) return;
    Modal.confirm({
      title: "删除文件",
      content: `确认删除 ${node.display_name ?? node.name}？`,
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        await api.deleteWorkspaceFile(workspaceId, node.id);
        message.success("已删除");
        await load();
      },
    });
  };

  const attach = (node: WorkspaceFileNode) => {
    if (node.type !== "file") return;
    const fileId = node.id.startsWith("file:") ? ` file_id=${node.id.slice(5)}` : "";
    onAttachReference(`@file(${node.path}${fileId}) `);
  };

  const favorite = async (node: WorkspaceFileNode) => {
    if (!workspaceId) return;
    await api.favoriteWorkspaceFile(workspaceId, node.id, !node.favorite);
    await load();
  };

  const createFolder = () => {
    if (!workspaceId) return;
    let name = "";
    let parent = "files";
    Modal.confirm({
      title: "新建文件夹",
      content: (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Select
            defaultValue={parent}
            options={directories}
            onChange={(value) => {
              parent = value;
            }}
          />
          <Input
            placeholder="文件夹名称"
            autoFocus
            onChange={(event) => {
              name = event.target.value;
            }}
          />
        </Space>
      ),
      okText: "创建",
      onOk: async () => {
        await api.createWorkspaceFolder(workspaceId, parent, name);
        message.success("文件夹已创建");
        await load();
      },
    });
  };

  const moveSelected = () => {
    if (!workspaceId || !checkedKeys.length) return;
    let target = "files";
    Modal.confirm({
      title: "移动到",
      content: (
        <Select
          style={{ width: "100%" }}
          defaultValue={target}
          options={directories}
          onChange={(value) => {
            target = value;
          }}
        />
      ),
      okText: "移动",
      onOk: async () => {
        await api.moveWorkspaceFiles(workspaceId, checkedKeys, target);
        setCheckedKeys([]);
        message.success("已移动所选文件");
        await load();
      },
    });
  };

  const bulkDelete = () => {
    if (!workspaceId || !checkedKeys.length) return;
    Modal.confirm({
      title: "批量删除",
      content: `确认删除已选择的 ${checkedKeys.length} 项？`,
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        await api.bulkDeleteWorkspaceFiles(workspaceId, checkedKeys);
        setCheckedKeys([]);
        message.success("已删除所选文件");
        await load();
      },
    });
  };

  const handleExpand = (keys: Key[]) => {
    const nextKeys = keys.map(String);
    setExpandedKeys(nextKeys);
    if (workspaceId) {
      window.localStorage.setItem(expandedStorageKey(workspaceId), JSON.stringify(nextKeys));
    }
  };

  return (
    <section className="workspace-files-page">
      <WorkspaceFileToolbar
        query={query}
        source={source}
        sources={[
          { label: "全部来源", value: "all" },
          ...sources.map((item) => ({ label: sourceLabel(item), value: item })),
        ]}
        stats={stats}
        loading={loading}
        checkedCount={checkedKeys.length}
        onBack={onBack}
        onQueryChange={setQuery}
        onSourceChange={setSource}
        onCreateFolder={createFolder}
        onMoveSelected={moveSelected}
        onBulkDelete={bulkDelete}
        onReload={load}
        onUploadFile={handleUpload}
      />
      <WorkspaceFileMap nodes={visibleNodes} />
      <div className="workspace-file-table-head">
        <span>名称</span>
        <span>来源</span>
        <span>大小</span>
        <span>修改时间</span>
        <span>操作</span>
      </div>
      <div className="workspace-file-tree-host">
        {loading ? (
          <div className="workspace-file-loading">
            <Spin />
          </div>
        ) : visibleNodes.length ? (
          <Tree
            blockNode
            checkable
            showIcon
            expandedKeys={expandedKeys}
            checkedKeys={checkedKeys}
            onExpand={handleExpand}
            onCheck={(keys) => {
              if (Array.isArray(keys)) setCheckedKeys(keys.map(String));
              else setCheckedKeys(keys.checked.map(String));
            }}
            treeData={toTreeData(visibleNodes, {
              onPreview: handlePreview,
              onDownload: handleDownload,
              onDelete: handleDelete,
              onAttach: attach,
              onRename: handleRename,
              onFavorite: favorite,
            })}
          />
        ) : (
          <Empty description="当前工作区暂无文件" />
        )}
      </div>
      <Modal
        title={
          preview && (
            <Space>
              <span>{preview.payload.filename ?? preview.node.display_name ?? preview.node.name}</span>
              <a onClick={() => handleDownload(preview.node)}>下载原文件</a>
            </Space>
          )
        }
        open={!!preview}
        onCancel={closePreview}
        footer={null}
        width={960}
      >
        {preview && <WorkspaceFilePreviewView preview={preview} />}
      </Modal>
    </section>
  );
}

function toTreeData(nodes: WorkspaceFileNode[], actions: FileRowActions): DataNode[] {
  return nodes.map((node) => ({
    key: node.id,
    icon: node.type === "directory" ? <FolderOpenOutlined /> : <FileOutlined />,
    title: <FileTreeRow node={node} actions={actions} />,
    children: node.children?.length ? toTreeData(node.children, actions) : undefined,
  }));
}

function normalizePreviewMode(
  payload: { mode?: string; content_type?: string; filename?: string },
  node: WorkspaceFileNode,
) {
  const mode = String(payload.mode || "").toLowerCase();
  const contentType = String(payload.content_type || node.mime_type || "").toLowerCase();
  const filename = String(payload.filename || node.name || node.path || "").toLowerCase();
  if (mode === "pdf" || contentType.includes("application/pdf") || filename.endsWith(".pdf")) return "pdf";
  if (mode === "image" || contentType.startsWith("image/")) return "image";
  if (mode === "html" || contentType.includes("html") || filename.endsWith(".html") || filename.endsWith(".htm")) {
    return "html";
  }
  if (mode === "office_text" || contentType.includes("officedocument") || /\.(docx|pptx|xlsx)$/.test(filename)) {
    return "office_text";
  }
  if (mode === "binary") return "binary";
  return mode || "text";
}

function isOfficeFileNode(node: WorkspaceFileNode) {
  const contentType = String(node.mime_type || "").toLowerCase();
  const filename = String(node.name || node.path || "").toLowerCase();
  return contentType.includes("officedocument") || /\.(docx|pptx|xlsx)$/.test(filename);
}

function expandedStorageKey(workspaceId: string) {
  return `agenthub.workspaceFiles.expanded.${workspaceId}`;
}

function previewText(payload: { text?: string; preview_text?: string }) {
  return payload.text || payload.preview_text || "";
}
