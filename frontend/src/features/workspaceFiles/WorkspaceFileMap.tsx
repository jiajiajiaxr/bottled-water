import { FileOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { Tag, Typography } from "antd";
import type { WorkspaceFileNode } from "../../types";
import {
  displayNodeName,
  displayNodePath,
  formatSize,
  sourceLabel,
} from "./workspaceFileUtils";

const { Text } = Typography;

type Props = {
  nodes: WorkspaceFileNode[];
};

export function WorkspaceFileMap({ nodes }: Props) {
  if (!nodes.length) return null;
  const stats = collectStats(nodes);

  return (
    <section className="workspace-file-map" aria-label="工作区文件地图">
      <div className="workspace-file-map-head">
        <div>
          <Text strong>文件地图</Text>
          <Text type="secondary">按来源和目录展示当前工作区文件</Text>
        </div>
        <Text type="secondary">
          {stats.directories} 个目录 · {stats.files} 个文件 · {formatSize(stats.size)}
        </Text>
      </div>
      <div className="workspace-file-map-body">
        {nodes.map((node) => (
          <FileMapNode key={node.id} node={node} depth={0} />
        ))}
      </div>
    </section>
  );
}

function FileMapNode({ node, depth }: { node: WorkspaceFileNode; depth: number }) {
  const isFile = node.type === "file";
  const children = node.children || [];

  return (
    <div className="workspace-file-map-node">
      <div
        className={`workspace-file-map-line ${isFile ? "is-file" : "is-dir"}`}
        style={{ paddingLeft: depth * 18 }}
      >
        <span className="workspace-file-map-branch" />
        {isFile ? <FileOutlined /> : <FolderOpenOutlined />}
        <span className="workspace-file-map-name" title={displayNodeName(node)}>
          {displayNodeName(node)}
        </span>
        {isFile ? (
          <>
            <Tag className="workspace-file-map-source">{sourceLabel(node.source)}</Tag>
            <Text type="secondary" className="workspace-file-map-meta">
              {formatSize(node.size ?? 0)}
            </Text>
          </>
        ) : (
          <Text type="secondary" className="workspace-file-map-meta">
            {children.length} 项
          </Text>
        )}
      </div>
      {isFile && (
        <Text
          type="secondary"
          className="workspace-file-map-path"
          style={{ paddingLeft: depth * 18 + 34 }}
          title={node.path}
        >
          {displayNodePath(node)}
        </Text>
      )}
      {children.map((child) => (
        <FileMapNode key={child.id} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

function collectStats(nodes: WorkspaceFileNode[]) {
  let files = 0;
  let directories = 0;
  let size = 0;

  const visit = (node: WorkspaceFileNode) => {
    if (node.type === "file") {
      files += 1;
      size += node.size || 0;
      return;
    }
    directories += 1;
    (node.children || []).forEach(visit);
  };

  nodes.forEach(visit);
  return { files, directories, size };
}
