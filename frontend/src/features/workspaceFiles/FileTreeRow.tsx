import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  StarFilled,
  StarOutlined,
  LinkOutlined,
  PlusCircleOutlined,
} from "@ant-design/icons";
import { Button, Tag, Tooltip, Typography } from "antd";
import type { WorkspaceFileNode } from "../../types";
import { formatDate, formatSize, sourceLabel } from "./workspaceFileUtils";

const { Text } = Typography;

export type FileRowActions = {
  onPreview: (node: WorkspaceFileNode) => void;
  onDownload: (node: WorkspaceFileNode) => void;
  onDelete: (node: WorkspaceFileNode) => void;
  onAttach: (node: WorkspaceFileNode) => void;
  onRename: (node: WorkspaceFileNode) => void;
  onFavorite: (node: WorkspaceFileNode) => void;
};

export function FileTreeRow({ node, actions }: { node: WorkspaceFileNode; actions: FileRowActions }) {
  const isFile = node.type === "file";
  return (
    <div className={`workspace-file-row ${isFile ? "is-file" : "is-dir"}`}>
      <div className="workspace-file-name-cell">
        <Text strong={isFile} ellipsis={{ tooltip: node.display_name ?? node.name }}>
          {node.display_name ?? node.name}
        </Text>
        {isFile && (
          <Text type="secondary" ellipsis={{ tooltip: node.path }}>
            {node.path}
          </Text>
        )}
      </div>
      <div>{isFile && <Tag className="workspace-file-source">{sourceLabel(node.source)}</Tag>}</div>
      <Text type="secondary" className="workspace-file-size">
        {isFile ? formatSize(node.size ?? 0) : ""}
      </Text>
      <Text type="secondary" className="workspace-file-date">
        {isFile ? formatDate(node.updated_at) : ""}
      </Text>
      <div className="workspace-file-actions">
        <FileActions node={node} actions={actions} />
      </div>
    </div>
  );
}

function FileActions({ node, actions }: { node: WorkspaceFileNode; actions: FileRowActions }) {
  const isFile = node.type === "file";
  return (
    <>
      <Tooltip title={node.favorite ? "取消收藏" : "收藏"}>
        <Button
          size="small"
          type="text"
          icon={node.favorite ? <StarFilled /> : <StarOutlined />}
          onClick={() => actions.onFavorite(node)}
        />
      </Tooltip>
      {isFile && (
        <Tooltip title="加入聊天上下文">
          <Button size="small" type="text" icon={<PlusCircleOutlined />} onClick={() => actions.onAttach(node)} />
        </Tooltip>
      )}
      <Tooltip title="复制路径">
        <Button
          size="small"
          type="text"
          icon={<LinkOutlined />}
          onClick={() => void navigator.clipboard.writeText(node.path)}
        />
      </Tooltip>
      <Tooltip title="重命名">
        <Button size="small" type="text" icon={<EditOutlined />} onClick={() => actions.onRename(node)} />
      </Tooltip>
      {isFile && (
        <>
          <Button size="small" onClick={() => actions.onPreview(node)}>
            预览
          </Button>
          <Tooltip title="下载">
            <Button size="small" type="text" icon={<DownloadOutlined />} onClick={() => actions.onDownload(node)} />
          </Tooltip>
        </>
      )}
      <Tooltip title="删除">
        <Button danger size="small" type="text" icon={<DeleteOutlined />} onClick={() => actions.onDelete(node)} />
      </Tooltip>
    </>
  );
}
