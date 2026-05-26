import { RobotOutlined } from "@ant-design/icons";
import { Button, Input, Space, Typography } from "antd";

const { Text } = Typography;
const { TextArea } = Input;

export function WorkflowAIGenerateCard({
  generating,
  workflowInstruction,
  onInstructionChange,
  onGenerate,
}: {
  generating: boolean;
  workflowInstruction: string;
  onInstructionChange: (value: string) => void;
  onGenerate: () => void;
}) {
  return (
    <Space direction="vertical" size={12} className="full-width">
      <div className="workflow-floating-field">
        <Text strong>AI 画布生成</Text>
        <Text type="secondary">
          写下你对群聊编排的要求，AI 会基于当前 Agent 和工具重排画布。
        </Text>
      </div>
      <TextArea
        value={workflowInstruction}
        onChange={(event) => onInstructionChange(event.target.value)}
        placeholder="例如：前后端并行，Reviewer 最后审查；日常问答跳过 Master。"
        autoSize={{ minRows: 5, maxRows: 8 }}
      />
      <Button
        type="primary"
        icon={<RobotOutlined />}
        loading={generating}
        onClick={onGenerate}
        data-testid="workflow-generate"
      >
        生成工作流
      </Button>
    </Space>
  );
}
