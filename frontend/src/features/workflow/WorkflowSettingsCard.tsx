import { PlayCircleOutlined, SaveOutlined } from "@ant-design/icons";
import { Button, Select, Space, Switch, Typography } from "antd";
import type { ConversationWorkflow } from "../../types";
import { workflowSettings } from "./utils";
import type { WorkflowValidationIssue } from "./validation";

const { Text } = Typography;

export function WorkflowSettingsCard({
  workflow,
  generating,
  validationIssues = [],
  onPatchSettings,
  onSave,
  onRun,
}: {
  workflow?: ConversationWorkflow;
  generating: boolean;
  validationIssues?: WorkflowValidationIssue[];
  onPatchSettings: (patch: Record<string, unknown>) => void;
  onSave: () => void;
  onRun: () => void;
}) {
  const settings = workflowSettings(workflow);
  const enabled = Boolean(settings.enabled);

  return (
    <Space direction="vertical" size={14} className="full-width">
      {validationIssues.length > 0 && (
        <div className="workflow-validation-summary">
          <Text strong type="danger">
            校验问题 {validationIssues.length}
          </Text>
          {validationIssues.slice(0, 8).map((issue) => (
            <Text
              key={issue.id}
              type={issue.severity === "error" ? "danger" : "warning"}
            >
              {issue.message}
            </Text>
          ))}
        </div>
      )}

      <div className="workflow-floating-setting-row">
        <div>
          <Text strong>启用状态</Text>
          <Text type="secondary">发送群聊消息时是否按此画布执行</Text>
        </div>
        <Switch
          checked={enabled}
          checkedChildren="启用"
          unCheckedChildren="停用"
          onChange={(checked) => onPatchSettings({ enabled: checked })}
        />
      </div>

      <div className="workflow-floating-setting-row">
        <div>
          <Text strong>发布状态</Text>
          <Text type="secondary">区分草稿和已确认版本</Text>
        </div>
        <Switch
          checked={Boolean(settings.published)}
          checkedChildren="已发布"
          unCheckedChildren="草稿"
          onChange={(checked) => onPatchSettings({ published: checked })}
        />
      </div>

      <div className="workflow-floating-field">
        <Text strong>输出模式</Text>
        <Select
          value={workflow?.output_mode ?? "independent_messages"}
          onChange={(value) => onPatchSettings({ output_mode: value })}
          options={[
            { label: "独立气泡回复", value: "independent_messages" },
            { label: "汇总回复", value: "aggregate" },
          ]}
        />
      </div>

      <Space wrap>
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={onSave}
          data-testid="workflow-save"
          disabled={generating}
        >
          保存画布
        </Button>
        <Button
          icon={<PlayCircleOutlined />}
          onClick={onRun}
          data-testid="workflow-run"
          disabled={generating}
        >
          运行
        </Button>
      </Space>
    </Space>
  );
}
