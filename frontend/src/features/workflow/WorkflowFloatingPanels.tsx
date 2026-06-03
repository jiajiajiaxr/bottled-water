import {
  ArrowLeftOutlined,
  AppstoreAddOutlined,
  CloseOutlined,
  CompressOutlined,
  CopyOutlined,
  DeleteOutlined,
  HistoryOutlined,
  ProfileOutlined,
  RobotOutlined,
  SettingOutlined,
  SlidersOutlined,
} from "@ant-design/icons";
import { Button, Space, Typography } from "antd";
import type { FormInstance } from "antd";
import type {
  ConversationWorkflow,
  WorkflowNode,
  WorkflowRun,
} from "../../types";
import { WorkflowAIGenerateCard } from "./WorkflowAIGenerateCard";
import { WorkflowFloatingButton } from "./WorkflowFloatingButton";
import { WorkflowHistoryCard, WorkflowRunLogCard } from "./WorkflowRuntimeCards";
import { WorkflowNodeConfigPanel } from "./WorkflowNodeConfigPanel";
import { WorkflowNodeLibraryCard } from "./WorkflowNodeLibraryCard";
import { WorkflowSettingsCard } from "./WorkflowSettingsCard";
import type { WorkflowValidationIssue } from "./validation";

const { Text } = Typography;

export type WorkflowFloatingPanelKey =
  | "library"
  | "ai"
  | "config"
  | "logs"
  | "settings"
  | "history";

const PANEL_TITLES: Record<WorkflowFloatingPanelKey, string> = {
  library: "节点库",
  ai: "AI生成",
  config: "当前节点配置",
  logs: "运行日志",
  settings: "工作流设置",
  history: "版本 / 历史",
};

export function WorkflowFloatingPanels({
  activePanel,
  workflow,
  generating,
  workflowInstruction,
  selectedNodeIds,
  selectedEdgeIds,
  editingNode,
  editingNodeState,
  latestRun,
  workflowRuns,
  workflowEdges,
  workflowJson,
  validationIssues = [],
  nodeForm,
  agentOptions,
  toolOptions,
  skillOptions,
  mcpServerOptions,
  mcpToolOptions,
  onActivePanelChange,
  onBack,
  onFitView,
  onInstructionChange,
  onPatchSettings,
  onSave,
  onGenerate,
  onRun,
  onNodeTypeChange,
  onAddNode,
  onCopySelection,
  onDeleteSelection,
  onSaveNode,
  onWorkflowJsonChange,
}: {
  activePanel?: WorkflowFloatingPanelKey;
  workflow?: ConversationWorkflow;
  generating: boolean;
  workflowInstruction: string;
  selectedNodeIds: string[];
  selectedEdgeIds: string[];
  editingNode?: WorkflowNode;
  editingNodeState?: WorkflowRun["node_states"][number];
  latestRun?: WorkflowRun;
  workflowRuns: WorkflowRun[];
  workflowEdges: string[][];
  workflowJson: string;
  validationIssues?: WorkflowValidationIssue[];
  nodeForm: FormInstance;
  agentOptions: Array<{ label: string; value: string }>;
  toolOptions: Array<{ label: string; value: string }>;
  skillOptions: Array<{ label: string; value: string }>;
  mcpServerOptions: Array<{ label: string; value: string }>;
  mcpToolOptions: Array<{ label: string; value: string }>;
  onActivePanelChange: (panel?: WorkflowFloatingPanelKey) => void;
  onBack: () => void;
  onFitView: () => void;
  onInstructionChange: (value: string) => void;
  onPatchSettings: (patch: Record<string, unknown>) => void;
  onSave: () => void;
  onGenerate: () => void;
  onRun: () => void;
  onNodeTypeChange: (value: string) => void;
  onAddNode: (type: string) => void;
  onCopySelection: () => void;
  onDeleteSelection: () => void;
  onSaveNode: () => void;
  onWorkflowJsonChange: (value: string) => void;
}) {
  const openPanel = (panel: WorkflowFloatingPanelKey) => {
    onActivePanelChange(activePanel === panel ? undefined : panel);
  };
  const leftMenuItems = [
    { key: "library", icon: <AppstoreAddOutlined />, disabled: generating },
    { key: "ai", icon: <RobotOutlined />, disabled: false },
    { key: "settings", icon: <SettingOutlined />, disabled: false },
    { key: "history", icon: <HistoryOutlined />, disabled: false },
  ] as const;
  const rightMenuItems = [
    { key: "config", icon: <SlidersOutlined />, disabled: !editingNode },
    { key: "logs", icon: <ProfileOutlined />, disabled: false },
  ] as const;
  const validationErrorCount = validationIssues.filter(
    (issue) => issue.severity === "error",
  ).length;
  const isSidePanel = activePanel && activePanel !== "logs";
  const isBottomPanel = activePanel === "logs";

  return (
    <>
      <nav className="workflow-floating-toolbar" aria-label="工作流工具栏">
        <WorkflowFloatingButton
          title="返回聊天"
          icon={<ArrowLeftOutlined />}
          onClick={onBack}
        />
        <div className="workflow-floating-toolbar-divider" />
        {leftMenuItems.map((item) => (
          <WorkflowFloatingButton
            key={item.key}
            title={PANEL_TITLES[item.key]}
            icon={item.icon}
            active={activePanel === item.key}
            disabled={item.disabled}
            loading={item.key === "ai" && generating}
            badgeCount={
              item.key === "settings" && validationErrorCount
                ? validationErrorCount
                : undefined
            }
            onClick={() => openPanel(item.key)}
          />
        ))}
        <div className="workflow-floating-toolbar-divider" />
        <WorkflowFloatingButton
          title="适配画布"
          icon={<CompressOutlined />}
          onClick={onFitView}
        />
        <WorkflowFloatingButton
          title="复制所选节点"
          icon={<CopyOutlined />}
          disabled={!selectedNodeIds.length || generating}
          onClick={onCopySelection}
        />
        <WorkflowFloatingButton
          title="删除所选内容"
          icon={<DeleteOutlined />}
          danger
          disabled={!selectedNodeIds.length && !selectedEdgeIds.length}
          onClick={onDeleteSelection}
        />
        <div className="workflow-floating-toolbar-divider" />
        {rightMenuItems.map((item) => (
          <WorkflowFloatingButton
            key={item.key}
            title={PANEL_TITLES[item.key]}
            icon={item.icon}
            active={activePanel === item.key}
            disabled={item.disabled}
            placement="left"
            onClick={() => openPanel(item.key)}
          />
        ))}
      </nav>
      <section
        className="workflow-floating-card"
        style={{
          opacity: isSidePanel ? 1 : 0,
          pointerEvents: isSidePanel ? "auto" : "none",
          transform: isSidePanel ? "translateX(0)" : "translateX(20px)",
          transition: "opacity 0.2s ease, transform 0.2s ease",
        }}
      >
        <header className="workflow-floating-card-header">
          <Text strong>{isSidePanel ? PANEL_TITLES[activePanel!] : ""}</Text>
          <Button
            type="text"
            size="small"
            icon={<CloseOutlined />}
            onClick={() => onActivePanelChange(undefined)}
          />
        </header>
        <div className="workflow-floating-card-body" key={activePanel}>
          {activePanel === "library" && (
            <WorkflowNodeLibraryCard
              disabled={generating}
              onAddNode={(type) => {
                onNodeTypeChange(type);
                onAddNode(type);
              }}
            />
          )}
          {activePanel === "ai" && (
            <WorkflowAIGenerateCard
              generating={generating}
              workflowInstruction={workflowInstruction}
              onInstructionChange={onInstructionChange}
              onGenerate={onGenerate}
            />
          )}
          {activePanel === "config" && (
            <WorkflowNodeConfigPanel
              nodeForm={nodeForm}
              editingNode={editingNode}
              editingNodeState={editingNodeState}
              latestRun={latestRun}
              workflowEdges={workflowEdges}
              workflowJson={workflowJson}
              agentOptions={agentOptions}
              toolOptions={toolOptions}
              skillOptions={skillOptions}
              mcpServerOptions={mcpServerOptions}
              mcpToolOptions={mcpToolOptions}
              onSaveNode={onSaveNode}
              onWorkflowJsonChange={onWorkflowJsonChange}
              className="workflow-floating-config"
              showRunState={false}
              showWorkflowJson={false}
              extraActions={
                <Space wrap>
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
                </Space>
              }
            />
          )}
          {activePanel === "settings" && (
            <WorkflowSettingsCard
              workflow={workflow}
              generating={generating}
              validationIssues={validationIssues}
              onPatchSettings={onPatchSettings}
              onSave={onSave}
              onRun={onRun}
            />
          )}
          {activePanel === "history" && (
            <WorkflowHistoryCard workflowRuns={workflowRuns} />
          )}
        </div>
      </section>
      <section
        className="workflow-floating-bottom"
        style={{
          opacity: isBottomPanel ? 1 : 0,
          pointerEvents: isBottomPanel ? "auto" : "none",
          transform: isBottomPanel ? "translateX(-50%) translateY(0)" : "translateX(-50%) translateY(20px)",
          transition: "opacity 0.2s ease, transform 0.2s ease",
        }}
      >
        <header className="workflow-floating-bottom-header">
          <Text strong>运行日志</Text>
          <Button
            type="text"
            size="small"
            icon={<CloseOutlined />}
            onClick={() => onActivePanelChange(undefined)}
          />
        </header>
        <div className="workflow-floating-bottom-body">
          <WorkflowRunLogCard
            latestRun={latestRun}
            editingNodeState={editingNodeState}
          />
        </div>
      </section>
    </>
  );
}
