import { SearchOutlined } from "@ant-design/icons";
import { Button, Empty, Input, Space, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import {
  WORKFLOW_NODE_TYPE_LABEL,
  WORKFLOW_NODE_TYPE_OPTIONS,
} from "../../lib/workflow";

const { Text } = Typography;

const NODE_OPTIONS = [
  { label: "Start", value: "start", description: "工作流入口" },
  ...WORKFLOW_NODE_TYPE_OPTIONS.map((option) => ({
    ...option,
    description: nodeDescription(option.value),
  })),
  { label: "End", value: "end", description: "结束与汇总输出" },
];

function nodeDescription(type: string) {
  const descriptions: Record<string, string> = {
    agent: "调用群聊 Agent 的 Function Call Loop",
    tool: "执行内置工具或自定义工具",
    skill: "运行工作区 Skill",
    mcp: "调用 MCP Server 工具",
    condition: "按表达式分支",
    loop: "重复执行子流程",
    review: "审查上游输出",
    artifact: "生成或导出产物",
  };
  return descriptions[type] ?? "添加工作流节点";
}

export function WorkflowNodeLibraryCard({
  disabled,
  onAddNode,
}: {
  disabled?: boolean;
  onAddNode: (type: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    if (!keyword) return NODE_OPTIONS;
    return NODE_OPTIONS.filter((option) => {
      const label = WORKFLOW_NODE_TYPE_LABEL[option.value] ?? option.label;
      return `${label} ${option.value} ${option.description}`
        .toLowerCase()
        .includes(keyword);
    });
  }, [query]);

  return (
    <Space direction="vertical" size={12} className="full-width">
      <Input
        allowClear
        prefix={<SearchOutlined />}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="搜索节点类型"
      />
      <div className="workflow-node-library-list">
        {filtered.length ? (
          filtered.map((option) => (
            <Button
              key={option.value}
              className="workflow-node-library-item"
              disabled={disabled}
              draggable={!disabled}
              onClick={() => onAddNode(option.value)}
              onDragStart={(event) => {
                event.dataTransfer.setData(
                  "application/x-agenthub-node",
                  option.value,
                );
                event.dataTransfer.effectAllowed = "copy";
              }}
            >
              <span>
                <Text strong>
                  {WORKFLOW_NODE_TYPE_LABEL[option.value] ?? option.label}
                </Text>
                <Text type="secondary">{option.description}</Text>
              </span>
              <Tag>{option.value}</Tag>
            </Button>
          ))
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无匹配节点" />
        )}
      </div>
      <Text type="secondary">点击添加，或拖到画布空白处快速创建节点。</Text>
    </Space>
  );
}
