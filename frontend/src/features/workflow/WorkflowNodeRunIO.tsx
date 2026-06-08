import { Empty, Space, Tag, Typography } from "antd";
import type { WorkflowRun } from "../../types";
import { statusTagColor } from "./utils";

const { Text } = Typography;

type WorkflowNodeState = WorkflowRun["node_states"][number];

function hasDisplayValue(value: unknown): boolean {
  if (value === undefined || value === null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function formatValue(value: unknown): string {
  if (!hasDisplayValue(value)) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function NodeIoBlock({
  label,
  value,
  emptyText,
}: {
  label: string;
  value: unknown;
  emptyText: string;
}) {
  const text = formatValue(value);
  return (
    <section className="workflow-node-io-block">
      <Text strong>{label}</Text>
      {text ? (
        <pre className="workflow-node-output">{text}</pre>
      ) : (
        <div className="workflow-node-io-empty">
          <Text type="secondary">{emptyText}</Text>
        </div>
      )}
    </section>
  );
}

export function WorkflowNodeRunIO({
  nodeState,
  run,
  emptyDescription = "暂无节点输入输出记录",
}: {
  nodeState?: WorkflowNodeState;
  run?: WorkflowRun;
  emptyDescription?: string;
}) {
  if (!nodeState) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={emptyDescription}
      />
    );
  }

  const runTime = run?.completed_at ?? run?.started_at ?? run?.created_at;

  return (
    <Space direction="vertical" size={10} className="workflow-node-io full-width">
      <div className="workflow-node-io-header">
        <Space wrap>
          <Text strong>{nodeState.title ?? nodeState.id}</Text>
          <Tag color={statusTagColor(nodeState.status)}>{nodeState.status}</Tag>
          {typeof nodeState.progress === "number" && <Tag>{nodeState.progress}%</Tag>}
          {run?.status && <Tag color={statusTagColor(run.status)}>run {run.status}</Tag>}
        </Space>
        {runTime && <Text type="secondary">{runTime}</Text>}
      </div>

      {nodeState.message && <Text type="secondary">{nodeState.message}</Text>}
      {nodeState.error && <Text type="danger">{nodeState.error}</Text>}

      <div className="workflow-node-io-grid">
        <NodeIoBlock
          label="节点输入"
          value={nodeState.input}
          emptyText="这次记录里没有保存输入"
        />
        <NodeIoBlock
          label="节点输出"
          value={nodeState.output}
          emptyText="这次记录里没有保存输出"
        />
      </div>
    </Space>
  );
}
