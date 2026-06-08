import { Empty, Space, Tag, Typography } from "antd";
import type { TabsProps } from "antd";
import type { WorkflowRun } from "../../types";
import { WorkflowNodeRunIO } from "./WorkflowNodeRunIO";
import { statusTagColor } from "./utils";

const { Text } = Typography;

export function WorkflowRunPanels({
  editingNodeState,
  editingNodeLastState,
  editingNodeLastRun,
  latestRun,
  workflowRuns,
}: {
  editingNodeState?: WorkflowRun["node_states"][number];
  editingNodeLastState?: WorkflowRun["node_states"][number];
  editingNodeLastRun?: WorkflowRun;
  latestRun?: WorkflowRun;
  workflowRuns: WorkflowRun[];
}): TabsProps["items"] {
  return [
    {
      key: "logs",
      label: "运行日志",
      children: (
        <div className="workflow-run-log">
          {(latestRun?.events ?? []).length ? (
            latestRun?.events.map((event, index) => (
              <pre key={`${event.type ?? "event"}-${index}`}>
                {JSON.stringify(event, null, 2)}
              </pre>
            ))
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无运行日志"
            />
          )}
        </div>
      ),
    },
    {
      key: "io",
      label: "节点输入输出",
      children: (
        <WorkflowNodeRunIO
          nodeState={editingNodeLastState ?? editingNodeState}
          run={editingNodeLastRun ?? latestRun}
        />
      ),
    },
    {
      key: "history",
      label: "历史版本",
      children: (
        <Space direction="vertical" className="full-width">
          {workflowRuns.length ? (
            workflowRuns.map((run) => (
              <div className="workflow-run-history" key={run.id}>
                <Space>
                  <Tag color={statusTagColor(run.status)}>{run.status}</Tag>
                  <Text>{run.progress}%</Text>
                  <Text type="secondary">{run.created_at ?? run.started_at}</Text>
                </Space>
              </div>
            ))
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无运行历史"
            />
          )}
        </Space>
      ),
    },
  ];
}
