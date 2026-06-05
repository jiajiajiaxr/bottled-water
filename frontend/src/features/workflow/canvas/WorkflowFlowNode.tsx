import {
  Handle,
  Position,
  type Node as FlowNode,
  type NodeProps,
} from "@xyflow/react";
import { Tag, Typography } from "antd";
import type { MouseEvent, PointerEvent } from "react";
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
  canReceiveConnection?: boolean;
  connectingSourceId?: string;
  connectingTargetId?: string;
  onStartConnection?: (
    nodeId: string,
    event: PointerEvent<HTMLElement>,
  ) => void;
  onStartConnectionFromMouse?: (
    nodeId: string,
    event: MouseEvent<HTMLElement>,
  ) => void;
  onArmConnection?: (nodeId: string, event: MouseEvent<HTMLElement>) => void;
  onCompleteConnection?: (
    nodeId: string,
    event: MouseEvent<HTMLElement> | PointerEvent<HTMLElement>,
  ) => void;
};

export function WorkflowFlowNode({
  data,
}: NodeProps<FlowNode<WorkflowFlowNodeData>>) {
  const node = data.workflowNode;
  const nodeId = String(node.id);
  const canReceive = data.nodeType !== "start";
  const canEmit = data.nodeType !== "end";
  const isConnectingSource = data.connectingSourceId === nodeId;
  const isConnectingTarget = data.connectingTargetId === nodeId;
  return (
    <>
      {canReceive && (
        <>
          <Handle
            id="input"
            type="target"
            position={Position.Left}
            className="xy-workflow-anchor-handle xy-workflow-anchor-input"
          />
          <button
            type="button"
            title="接收上游输出"
            aria-label="接收上游输出"
            data-workflow-port="input"
            data-node-id={nodeId}
            className={[
              "xy-workflow-port",
              "xy-workflow-port-input",
              data.canReceiveConnection ? "is-connectable-target" : "",
              isConnectingTarget ? "is-hot-target" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onPointerDown={(event) => {
              event.stopPropagation();
            }}
          />
        </>
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
          <div className="xy-workflow-node-badges">
            <Tag className="xy-workflow-node-type">
              {WORKFLOW_NODE_TYPE_LABEL[data.nodeType] ?? data.nodeType}
            </Tag>
            <Tag className="xy-workflow-node-state">
              {data.status}
            </Tag>
          </div>
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
            {typeof data.progress === "number" ? ` / ${data.progress}%` : ""}
          </Text>
        </div>
      </div>
      {canEmit && (
        <>
          <Handle
            id="output"
            type="source"
            position={Position.Right}
            className="xy-workflow-anchor-handle xy-workflow-anchor-output"
          />
          <button
            type="button"
            title="点击选择或拖拽创建连线"
            aria-label="点击选择或拖拽创建连线"
            data-workflow-port="output"
            data-node-id={nodeId}
            className={[
              "xy-workflow-port",
              "xy-workflow-port-output",
              isConnectingSource ? "is-connecting-source" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onPointerDown={(event) => {
              data.onStartConnection?.(nodeId, event);
            }}
            onMouseDown={(event) => {
              data.onStartConnectionFromMouse?.(nodeId, event);
            }}
            onClick={(event) => {
              data.onArmConnection?.(nodeId, event);
            }}
          />
        </>
      )}
    </>
  );
}
