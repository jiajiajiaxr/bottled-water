import {
  Handle,
  Position,
  type Node as FlowNode,
  type NodeProps,
} from "@xyflow/react";
import { Tag, Typography } from "antd";
import type { WorkflowNode } from "../../../types";
import { WORKFLOW_NODE_TYPE_LABEL } from "../../../lib/workflow";

const { Text } = Typography;

export type WorkflowFlowNodeData = {
  workflowNode: WorkflowNode;
  nodeType: string;
  status: string;
  statusColor: string;
  message: string;
  progress?: number;
  onNodeClick?: (node: WorkflowNode) => void;
};

export function WorkflowFlowNode({
  data,
}: NodeProps<FlowNode<WorkflowFlowNodeData>>) {
  const node = data.workflowNode;
  const canReceive = data.nodeType !== "start";
  const canEmit = data.nodeType !== "end";
  return (
    <>
      {canReceive && (
        <Handle
          id="input"
          type="target"
          position={Position.Left}
          className="xy-workflow-handle xy-workflow-handle-input"
        />
      )}
      <div
        className="xy-workflow-node-content"
        onClick={(event) => {
          event.stopPropagation();
          data.onNodeClick?.(node);
        }}
      >
        <div className="xy-workflow-node-header">
          <Text strong className="xy-workflow-node-title">
            {node.title}
          </Text>
          <Tag className="xy-workflow-node-type" color={data.statusColor}>
            {WORKFLOW_NODE_TYPE_LABEL[data.nodeType] ?? data.nodeType}
          </Tag>
        </div>
        <Text className="xy-workflow-node-meta" type="secondary">
          {data.message}
        </Text>
        <div className="xy-workflow-node-footer">
          <span style={{ backgroundColor: data.statusColor }} />
          <Text
            className="xy-workflow-node-status"
            type={data.status === "failed" ? "danger" : "secondary"}
          >
            {data.status}
            {typeof data.progress === "number" ? ` / ${data.progress}%` : ""}
          </Text>
        </div>
      </div>
      {canEmit && (
        <Handle
          id="output"
          type="source"
          position={Position.Right}
          className="xy-workflow-handle xy-workflow-handle-output"
        />
      )}
    </>
  );
}

