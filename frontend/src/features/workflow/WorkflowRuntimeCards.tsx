import { Empty, Progress, Space, Tag, Typography } from "antd";
import type { WorkflowRun } from "../../types";
import { WorkflowNodeRunIO } from "./WorkflowNodeRunIO";
import { statusTagColor } from "./utils";

const { Text } = Typography;

export function WorkflowRunLogCard({
  latestRun,
  editingNodeState,
  editingNodeLastState,
  editingNodeLastRun,
}: {
  latestRun?: WorkflowRun;
  editingNodeState?: WorkflowRun["node_states"][number];
  editingNodeLastState?: WorkflowRun["node_states"][number];
  editingNodeLastRun?: WorkflowRun;
}) {
  if (!latestRun) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无运行记录" />;
  }

  const nodeStates = latestRun.node_states ?? [];
  const events = latestRun.events ?? [];

  return (
    <Space direction="vertical" size={12} className="full-width">
      <div className="workflow-floating-run-summary">
        <Space wrap>
          <Tag color={statusTagColor(latestRun.status)}>{latestRun.status}</Tag>
          <Text type="secondary">{latestRun.progress}% complete</Text>
        </Space>
        <Progress percent={latestRun.progress} size="small" />
      </div>

      <div className="workflow-runtime-section">
        <Text strong>节点输入输出</Text>
        <WorkflowNodeRunIO
          nodeState={editingNodeLastState ?? editingNodeState}
          run={editingNodeLastRun ?? latestRun}
        />
      </div>

      <div className="workflow-runtime-section">
        <Text strong>节点状态</Text>
        <Space direction="vertical" size={8} className="full-width">
          {nodeStates.length ? (
            nodeStates.map((state) => (
              <div className="workflow-runtime-node" key={state.id}>
                <Space wrap>
                  <Text strong>{state.title ?? state.id}</Text>
                  <Tag color={statusTagColor(state.status)}>{state.status}</Tag>
                  {typeof state.progress === "number" && <Tag>{state.progress}%</Tag>}
                </Space>
                {state.error && <Text type="danger">{state.error}</Text>}
              </div>
            ))
          ) : (
            <Text type="secondary">暂无节点状态</Text>
          )}
        </Space>
      </div>

      <div className="workflow-runtime-section">
        <Text strong>事件流</Text>
        <div className="workflow-run-log">
          {events.length ? (
            events.map((event, index) => (
              <pre key={`${event.type ?? "event"}-${index}`}>
                {JSON.stringify(event, null, 2)}
              </pre>
            ))
          ) : (
            <Text type="secondary">暂无事件</Text>
          )}
        </div>
      </div>
    </Space>
  );
}

export function WorkflowHistoryCard({
  workflowRuns,
}: {
  workflowRuns: WorkflowRun[];
}) {
  return (
    <Space direction="vertical" size={10} className="full-width">
      {workflowRuns.length ? (
        workflowRuns.map((run) => (
          <div className="workflow-run-history" key={run.id}>
            <Space wrap>
              <Tag color={statusTagColor(run.status)}>{run.status}</Tag>
              <Text>{run.progress}%</Text>
              <Text type="secondary">{run.created_at ?? run.started_at}</Text>
            </Space>
          </div>
        ))
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史版本" />
      )}
    </Space>
  );
}
