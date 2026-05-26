import {
  ArrowLeftOutlined,
  CompressOutlined,
  CopyOutlined,
  DeleteOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { Button, Input, Select, Space, Switch, Tooltip, Typography } from "antd";
import { WORKFLOW_NODE_TYPE_OPTIONS } from "../../lib/workflow";
import type { ConversationWorkflow } from "../../types";
import { workflowSettings } from "./utils";

const { Text } = Typography;
const { TextArea } = Input;

export function WorkflowModeToolbar({
  workflow,
  generating,
  workflowInstruction,
  newNodeType,
  selectedNodeIds,
  selectedEdgeIds,
  onBack,
  onSave,
  onGenerate,
  onRun,
  onFitView,
  onInstructionChange,
  onNodeTypeChange,
  onAddNode,
  onCopySelection,
  onDeleteSelection,
  onPatchSettings,
}: {
  workflow?: ConversationWorkflow;
  generating: boolean;
  workflowInstruction: string;
  newNodeType: string;
  selectedNodeIds: string[];
  selectedEdgeIds: string[];
  onBack: () => void;
  onSave: () => void;
  onGenerate: () => void;
  onRun: () => void;
  onFitView: () => void;
  onInstructionChange: (value: string) => void;
  onNodeTypeChange: (value: string) => void;
  onAddNode: (type: string) => void;
  onCopySelection: () => void;
  onDeleteSelection: () => void;
  onPatchSettings: (patch: Record<string, unknown>) => void;
}) {
  const settings = workflowSettings(workflow);
  const nodeOptions = [
    { label: "Start", value: "start" },
    ...WORKFLOW_NODE_TYPE_OPTIONS,
    { label: "End", value: "end" },
  ];
  return (
    <aside className="workflow-mode-toolbar">
      <Tooltip title="返回聊天">
        <Button icon={<ArrowLeftOutlined />} onClick={onBack} block>
          聊天
        </Button>
      </Tooltip>
      <Space direction="vertical" size={8} className="full-width">
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={onSave}
          data-testid="workflow-save"
          block
        >
          保存
        </Button>
        <Button
          icon={<RobotOutlined />}
          loading={generating}
          onClick={onGenerate}
          data-testid="workflow-generate"
          block
        >
          AI生成
        </Button>
        <Button
          icon={<PlayCircleOutlined />}
          onClick={onRun}
          data-testid="workflow-run"
          block
        >
          运行
        </Button>
        <Button icon={<CompressOutlined />} onClick={onFitView} block>
          适配
        </Button>
      </Space>
      <div className="workflow-mode-switches">
        <Text type="secondary">状态</Text>
        <Switch
          checked={settings.enabled !== false}
          checkedChildren="启用"
          unCheckedChildren="停用"
          onChange={(checked) => onPatchSettings({ enabled: checked })}
        />
        <Switch
          checked={Boolean(settings.published)}
          checkedChildren="已发布"
          unCheckedChildren="草稿"
          onChange={(checked) => onPatchSettings({ published: checked })}
        />
      </div>
      <div className="workflow-mode-add">
        <Text type="secondary">节点</Text>
        <Select
          value={newNodeType}
          onChange={onNodeTypeChange}
          options={nodeOptions}
          size="small"
        />
        <Button
          icon={<PlusOutlined />}
          onClick={() => onAddNode(newNodeType)}
          disabled={generating}
          block
        >
          添加
        </Button>
      </div>
      <Space direction="vertical" size={8} className="full-width">
        <Button
          icon={<CopyOutlined />}
          disabled={!selectedNodeIds.length}
          onClick={onCopySelection}
          block
        >
          复制
        </Button>
        <Button
          danger
          icon={<DeleteOutlined />}
          disabled={!selectedNodeIds.length && !selectedEdgeIds.length}
          onClick={onDeleteSelection}
          block
        >
          删除
        </Button>
      </Space>
      <div className="workflow-mode-output">
        <Text type="secondary">回复</Text>
        <Select
          value={workflow?.output_mode ?? "independent_messages"}
          onChange={(value) => {
            if (!workflow) return;
            onPatchSettings({ output_mode: value });
          }}
          options={[
            { label: "独立气泡", value: "independent_messages" },
            { label: "汇总", value: "aggregate" },
          ]}
          size="small"
        />
      </div>
      <TextArea
        value={workflowInstruction}
        onChange={(event) => onInstructionChange(event.target.value)}
        placeholder="给 AI 的画布意见"
        autoSize={{ minRows: 3, maxRows: 5 }}
      />
    </aside>
  );
}
