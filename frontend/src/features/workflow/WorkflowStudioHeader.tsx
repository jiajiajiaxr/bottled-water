import {
  ArrowLeftOutlined,
  PlayCircleOutlined,
  RobotOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { Button, Space, Switch, Tag, Typography } from "antd";
import type { Conversation, ConversationWorkflow } from "../../types";
import { workflowSettings } from "./utils";

const { Text, Title } = Typography;

export function WorkflowStudioHeader({
  conversation,
  workflow,
  generating,
  onBack,
  onGenerate,
  onRun,
  onSave,
  onPatchSettings,
}: {
  conversation?: Conversation;
  workflow?: ConversationWorkflow;
  generating: boolean;
  onBack: () => void;
  onGenerate: () => void;
  onRun: () => void;
  onSave: () => void;
  onPatchSettings: (patch: Record<string, unknown>) => void;
}) {
  const settings = workflowSettings(workflow);
  return (
    <div className="workflow-studio-header">
      <Space align="center" wrap>
        <Button
          icon={<ArrowLeftOutlined />}
          onClick={onBack}
          data-testid="workflow-back"
        >
          返回群聊
        </Button>
        <div>
          <Title level={4}>{conversation?.title ?? "工作流画布"}</Title>
          <Text type="secondary">
            conversation.extra.workflow · {workflow?.mode ?? "workflow"}
          </Text>
        </div>
        <Tag color={settings.enabled === false ? "default" : "green"}>
          {settings.enabled === false ? "未启用" : "已启用"}
        </Tag>
        <Tag color={settings.published ? "blue" : "default"}>
          {settings.published ? "已发布" : "草稿"}
        </Tag>
      </Space>
      <Space wrap>
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
        <Button icon={<RobotOutlined />} loading={generating} onClick={onGenerate}>
          AI 生成
        </Button>
        <Button type="primary" icon={<SaveOutlined />} onClick={onSave}>
          保存
        </Button>
        <Button icon={<PlayCircleOutlined />} onClick={onRun}>
          运行
        </Button>
      </Space>
    </div>
  );
}
