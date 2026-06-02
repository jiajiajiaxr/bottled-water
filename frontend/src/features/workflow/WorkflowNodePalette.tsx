import { PlusOutlined } from "@ant-design/icons";
import { Button, Typography } from "antd";
import { WORKFLOW_NODE_TYPE_OPTIONS } from "../../lib/workflow";

const { Text } = Typography;

export function WorkflowNodePalette({
  disabled,
  onAdd,
}: {
  disabled?: boolean;
  onAdd: (type: string) => void;
}) {
  const options = [
    { label: "Start", value: "start" },
    ...WORKFLOW_NODE_TYPE_OPTIONS,
    { label: "End", value: "end" },
  ];
  return (
    <aside className="workflow-studio-left">
      <Text strong>节点类型</Text>
      <div className="workflow-node-palette">
        {options.map((option) => (
          <Button
            key={option.value}
            icon={<PlusOutlined />}
            onClick={() => onAdd(option.value)}
            disabled={disabled}
            block
          >
            {option.label}
          </Button>
        ))}
      </div>
      <Text type="secondary">
        普通拖拽移动节点，Shift + 拖拽框选，多选后可复制或删除。
      </Text>
    </aside>
  );
}
