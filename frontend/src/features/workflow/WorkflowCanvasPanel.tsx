import {
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import { Button, Empty, Select, Space, Tabs, Input } from "antd";
import { WORKFLOW_NODE_TYPE_OPTIONS } from "../../lib/workflow";
import { WorkflowCanvas } from "../chat/components/drawers/WorkflowCanvas";
import type {
  ConversationWorkflow,
  WorkflowNode,
  WorkflowRun,
} from "../../types";
import { WorkflowRunPanels } from "./WorkflowRunPanels";

const { TextArea } = Input;

export function WorkflowCanvasPanel({
  workflow,
  latestRun,
  workflowGenerating,
  workflowInstruction,
  newNodeType,
  selectedNodeIds,
  selectedEdgeIds,
  editingNodeState,
  workflowRuns,
  onInstructionChange,
  onNodeTypeChange,
  onAddNode,
  onCopySelection,
  onDeleteSelection,
  onWorkflowChange,
  onOpenNode,
  onClearSelection,
  onSelectionChange,
}: {
  workflow?: ConversationWorkflow;
  latestRun?: WorkflowRun;
  workflowGenerating: boolean;
  workflowInstruction: string;
  newNodeType: string;
  selectedNodeIds: string[];
  selectedEdgeIds: string[];
  editingNodeState?: WorkflowRun["node_states"][number];
  workflowRuns: WorkflowRun[];
  onInstructionChange: (value: string) => void;
  onNodeTypeChange: (value: string) => void;
  onAddNode: (type: string) => void;
  onCopySelection: () => void;
  onDeleteSelection: () => void;
  onWorkflowChange: (workflow: ConversationWorkflow) => void;
  onOpenNode: (node: WorkflowNode) => void;
  onClearSelection: () => void;
  onSelectionChange: (nodeIds: string[], edgeIds: string[]) => void;
}) {
  const nodeOptions = [
    { label: "Start", value: "start" },
    ...WORKFLOW_NODE_TYPE_OPTIONS,
    { label: "End", value: "end" },
  ];

  return (
    <main className="workflow-studio-canvas-wrap">
      <div className="workflow-studio-toolbar">
        <Space wrap>
          <Select
            value={newNodeType}
            onChange={onNodeTypeChange}
            options={nodeOptions}
            style={{ width: 180 }}
          />
          <Button icon={<PlusOutlined />} onClick={() => onAddNode(newNodeType)}>
            新增节点
          </Button>
          <Button
            icon={<CopyOutlined />}
            disabled={!selectedNodeIds.length}
            onClick={onCopySelection}
          >
            复制
          </Button>
          <Button
            danger
            icon={<DeleteOutlined />}
            disabled={!selectedNodeIds.length && !selectedEdgeIds.length}
            onClick={onDeleteSelection}
          >
            删除
          </Button>
          <Select
            value={workflow?.output_mode ?? "independent_messages"}
            onChange={(value) => {
              if (!workflow) return;
              onWorkflowChange({ ...workflow, output_mode: value });
            }}
            options={[
              { label: "独立气泡回复", value: "independent_messages" },
              { label: "汇总回复", value: "aggregate" },
            ]}
            style={{ width: 180 }}
          />
        </Space>
        <TextArea
          value={workflowInstruction}
          onChange={(event) => onInstructionChange(event.target.value)}
          placeholder="给 AI 的画布编排意见，例如：前后端并行，Reviewer 最后审查。"
          autoSize={{ minRows: 1, maxRows: 3 }}
        />
      </div>
      {workflow ? (
        <WorkflowCanvas
          workflow={workflow}
          latestRun={latestRun}
          locked={workflowGenerating}
          overlayText={workflowGenerating ? "AI 正在生成工作流…" : undefined}
          selectedNodeIds={selectedNodeIds}
          selectedEdgeIds={selectedEdgeIds}
          onChange={onWorkflowChange}
          onNodeClick={onOpenNode}
          onPaneClick={onClearSelection}
          onCopySelection={onCopySelection}
          onSelectionChange={onSelectionChange}
        />
      ) : (
        <Empty description="当前会话暂无工作流" />
      )}
      <Tabs
        className="workflow-studio-bottom"
        size="small"
        items={WorkflowRunPanels({
          editingNodeState,
          latestRun,
          workflowRuns,
        })}
      />
    </main>
  );
}
