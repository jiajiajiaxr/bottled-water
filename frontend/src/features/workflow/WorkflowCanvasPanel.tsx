import { Collapse, Empty, Tabs } from "antd";
import { WorkflowCanvas } from "../chat/components/drawers/WorkflowCanvas";
import type {
  ConversationWorkflow,
  WorkflowNode,
  WorkflowRun,
} from "../../types";
import type { WorkflowValidationIssue } from "./validation";
import { WorkflowRunPanels } from "./WorkflowRunPanels";

export function WorkflowCanvasPanel({
  workflow,
  latestRun,
  workflowGenerating,
  selectedNodeIds,
  selectedEdgeIds,
  editingNodeState,
  workflowRuns,
  validationIssues,
  fitViewSignal,
  showRuntimePanel = true,
  onCopySelection,
  onDropNodeType,
  onWorkflowChange,
  onOpenNode,
  onClearSelection,
  onSelectionChange,
}: {
  workflow?: ConversationWorkflow;
  latestRun?: WorkflowRun;
  workflowGenerating: boolean;
  selectedNodeIds: string[];
  selectedEdgeIds: string[];
  editingNodeState?: WorkflowRun["node_states"][number];
  workflowRuns: WorkflowRun[];
  validationIssues?: WorkflowValidationIssue[];
  fitViewSignal: number;
  showRuntimePanel?: boolean;
  onCopySelection: () => void;
  onDropNodeType?: (type: string, position?: { x: number; y: number }) => void;
  onWorkflowChange: (workflow: ConversationWorkflow) => void;
  onOpenNode: (node: WorkflowNode) => void;
  onClearSelection: () => void;
  onSelectionChange: (nodeIds: string[], edgeIds: string[]) => void;
}) {
  return (
    <main className="workflow-studio-canvas-wrap">
      {workflow ? (
        <WorkflowCanvas
          workflow={workflow}
          latestRun={latestRun}
          locked={workflowGenerating}
          overlayText={workflowGenerating ? "AI 正在生成工作流…" : undefined}
          fitViewSignal={fitViewSignal}
          selectedNodeIds={selectedNodeIds}
          selectedEdgeIds={selectedEdgeIds}
          validationIssues={validationIssues}
          onChange={onWorkflowChange}
          onDropNodeType={onDropNodeType}
          onNodeClick={onOpenNode}
          onPaneClick={onClearSelection}
          onCopySelection={onCopySelection}
          onSelectionChange={onSelectionChange}
        />
      ) : (
        <Empty description="当前会话暂无工作流" />
      )}
      {showRuntimePanel && (
        <Collapse
          className="workflow-studio-bottom"
          size="small"
          items={[
            {
              key: "runtime",
              label: "运行日志 / 节点输出 / 历史版本",
              children: (
                <Tabs
                  size="small"
                  items={WorkflowRunPanels({
                    editingNodeState,
                    latestRun,
                    workflowRuns,
                  })}
                />
              ),
            },
          ]}
        />
      )}
    </main>
  );
}
