import { FileOutlined, FolderOpenOutlined } from "@ant-design/icons";
import { Tag, Typography } from "antd";
import type { WorkspaceFileNode } from "../../types";
import { displayNodeName, formatSize, sourceLabel } from "./workspaceFileUtils";

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
          <Text type="secondary">按目录自上而下展示当前工作区文件结构</Text>
        </div>
        <Text type="secondary">
          {stats.directories} 个目录 · {stats.files} 个文件 · {formatSize(stats.size)}
        </Text>
      </div>
      <div className="workspace-file-map-body">
        <div className="workspace-file-map-forest">
          {nodes.map((node) => (
            <TreeNode key={node.id} node={node} />
          ))}
        </div>
      </div>
    </section>
  );
}

function TreeNode({ node }: { node: WorkspaceFileNode }) {
  const isFile = node.type === "file";
  const children = node.children ?? [];

  return (
    <div className={`workspace-file-chart-node ${isFile ? "is-file" : "is-dir"}`}>
      <div className="workspace-file-chart-card">
        <div className="workspace-file-chart-card-head">
          <span className="workspace-file-chart-icon">
            {isFile ? <FileOutlined /> : <FolderOpenOutlined />}
          </span>
          <span className="workspace-file-chart-name" title={displayNodeName(node)}>
            {displayNodeName(node)}
          </span>
        </div>
        <div className="workspace-file-chart-card-meta">
          {isFile ? (
            <>
              <Tag className="workspace-file-chart-tag">{sourceLabel(node.source)}</Tag>
              <Text type="secondary">{formatSize(node.size ?? 0)}</Text>
            </>
          ) : (
            <Text type="secondary">{children.length} 项</Text>
          )}
        </div>
      </div>

      {children.length ? (
        <div className="workspace-file-chart-children">
          {children.map((child) => (
            <div className="workspace-file-chart-child" key={child.id}>
              <TreeNode node={child} />
            </div>
          ))}
        </div>
      ) : null}
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
