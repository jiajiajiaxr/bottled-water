import { CheckCircleOutlined } from "@ant-design/icons";
import type { ReactNode } from "react";
import {
  Button,
  Empty,
  Form,
  Input,
  Progress,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import type { FormInstance } from "antd";
import { WORKFLOW_NODE_TYPE_OPTIONS } from "../../lib/workflow";
import type { WorkflowNode, WorkflowRun } from "../../types";
import { statusTagColor } from "./utils";

const { Text } = Typography;
const { TextArea } = Input;

export function WorkflowNodeConfigPanel({
  nodeForm,
  editingNode,
  editingNodeState,
  latestRun,
  workflowEdges,
  workflowJson,
  agentOptions,
  toolOptions,
  skillOptions,
  mcpServerOptions,
  mcpToolOptions,
  onSaveNode,
  onWorkflowJsonChange,
  className = "workflow-studio-right",
  showRunState = true,
  showWorkflowJson = true,
  extraActions,
}: {
  nodeForm: FormInstance;
  editingNode?: WorkflowNode;
  editingNodeState?: WorkflowRun["node_states"][number];
  latestRun?: WorkflowRun;
  workflowEdges: string[][];
  workflowJson: string;
  agentOptions: Array<{ label: string; value: string }>;
  toolOptions: Array<{ label: string; value: string }>;
  skillOptions: Array<{ label: string; value: string }>;
  mcpServerOptions: Array<{ label: string; value: string }>;
  mcpToolOptions: Array<{ label: string; value: string }>;
  onSaveNode: () => void;
  onWorkflowJsonChange: (value: string) => void;
  className?: string;
  showRunState?: boolean;
  showWorkflowJson?: boolean;
  extraActions?: ReactNode;
}) {
  return (
    <aside className={className}>
      <Text strong>节点配置</Text>
      {editingNode ? (
        <Form form={nodeForm} layout="vertical" className="workflow-node-config-form">
          <Space wrap>
            <Tag color={statusTagColor(editingNodeState?.status ?? editingNode.status)}>
              {editingNodeState?.status ?? editingNode.status ?? "queued"}
            </Tag>
            {typeof editingNodeState?.progress === "number" && (
              <Tag>{editingNodeState.progress}%</Tag>
            )}
          </Space>
          <Form.Item name="title" label="名称" rules={[{ required: true, message: "请输入节点名称" }]}>
            <Input maxLength={80} />
          </Form.Item>
          <Form.Item name="type" label="节点类型" rules={[{ required: true, message: "请选择节点类型" }]}>
            <Select
              options={[
                { label: "Start", value: "start" },
                ...WORKFLOW_NODE_TYPE_OPTIONS,
                { label: "End", value: "end" },
              ]}
            />
          </Form.Item>
          <Form.Item name="meta" label="说明">
            <TextArea rows={2} maxLength={300} />
          </Form.Item>
          <Form.Item shouldUpdate noStyle>
            {({ getFieldValue }) => (
              <NodeTypeFields
                type={getFieldValue("type")}
                agentOptions={agentOptions}
                toolOptions={toolOptions}
                skillOptions={skillOptions}
                mcpServerOptions={mcpServerOptions}
                mcpToolOptions={mcpToolOptions}
              />
            )}
          </Form.Item>
          <Form.Item
            name="input_mapping"
            label="输入映射"
            extra="支持 {{input}}、{{nodes.agent-frontend.text}}、{{upstream.text}}"
          >
            <TextArea rows={3} placeholder='例如 {"prompt": "{{input}}", "brief": "{{upstream.text}}"}' />
          </Form.Item>
          <Form.Item
            name="output_mapping"
            label="输出映射"
            extra="节点执行结果可用 {{output.text}} / {{output.result}} 引用"
          >
            <TextArea rows={3} placeholder='例如 {"text": "{{output.text}}", "summary": "{{output.summary}}"}' />
          </Form.Item>
          <Space wrap>
            <Form.Item name="failure_strategy" label="失败策略" className="workflow-inline-form-item">
              <Select
                options={[
                  { label: "停止后续", value: "stop" },
                  { label: "跳过继续", value: "continue" },
                  { label: "重试", value: "retry" },
                ]}
              />
            </Form.Item>
            <Form.Item name="retry" label="重试次数" className="workflow-inline-form-item">
              <Input type="number" min={0} max={3} />
            </Form.Item>
          </Space>
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={onSaveNode}>
            应用配置
          </Button>
          {extraActions}
        </Form>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击画布节点后在这里配置" />
      )}
      {showRunState && <RunStateCard latestRun={latestRun} workflowEdges={workflowEdges} />}
      {showWorkflowJson && (
        <div className="workflow-json-panel">
          <Text strong>Workflow JSON</Text>
          <TextArea rows={10} value={workflowJson} onChange={(event) => onWorkflowJsonChange(event.target.value)} />
        </div>
      )}
    </aside>
  );
}

function NodeTypeFields({
  type,
  agentOptions,
  toolOptions,
  skillOptions,
  mcpServerOptions,
  mcpToolOptions,
}: {
  type?: string;
  agentOptions: Array<{ label: string; value: string }>;
  toolOptions: Array<{ label: string; value: string }>;
  skillOptions: Array<{ label: string; value: string }>;
  mcpServerOptions: Array<{ label: string; value: string }>;
  mcpToolOptions: Array<{ label: string; value: string }>;
}) {
  return (
    <>
      {(type === "agent" || type === "review") && (
        <Form.Item name="agent_id" label="Agent">
          <Select allowClear showSearch options={agentOptions} placeholder="选择群聊中的 Agent" />
        </Form.Item>
      )}
      {type === "tool" && (
        <Form.Item name="tool_name" label="工具">
          <Select showSearch options={toolOptions} />
        </Form.Item>
      )}
      {type === "skill" && (
        <Form.Item name="skill_id" label="Skill">
          <Select showSearch options={skillOptions} />
        </Form.Item>
      )}
      {type === "mcp" && (
        <>
          <Form.Item name="mcp_server_id" label="MCP Server">
            <Select allowClear options={mcpServerOptions} />
          </Form.Item>
          <Form.Item name="mcp_tool_name" label="MCP Tool">
            <Select showSearch options={mcpToolOptions} />
          </Form.Item>
        </>
      )}
      {type === "condition" && (
        <Form.Item name="expression" label="条件表达式">
          <TextArea rows={2} placeholder="input.includes('需要审查')" />
        </Form.Item>
      )}
      {type === "loop" && (
        <Form.Item name="max_iterations" label="循环次数">
          <Input type="number" min={1} max={20} />
        </Form.Item>
      )}
      {type === "artifact" && (
        <Form.Item name="artifact_type" label="产物类型">
          <Select
            options={["html", "pdf", "docx", "xlsx", "pptx"].map((value) => ({
              label: value.toUpperCase(),
              value,
            }))}
          />
        </Form.Item>
      )}
    </>
  );
}

function RunStateCard({
  latestRun,
  workflowEdges,
}: {
  latestRun?: WorkflowRun;
  workflowEdges: string[][];
}) {
  return (
    <div className="workflow-studio-run-card">
      <Text strong>运行态</Text>
      {latestRun ? (
        <>
          <Space wrap>
            <Tag color={statusTagColor(latestRun.status)}>{latestRun.status}</Tag>
            <Text type="secondary">{latestRun.progress}% complete</Text>
          </Space>
          <Progress percent={latestRun.progress} status={latestRun.status === "failed" ? "exception" : undefined} />
          <div className="workflow-node-state-list">
            {(latestRun.node_states ?? []).map((node) => (
              <Tag key={node.id} color={statusTagColor(node.status)}>
                {node.title ?? node.id} · {node.status}
              </Tag>
            ))}
          </div>
        </>
      ) : (
        <Text type="secondary">尚未运行</Text>
      )}
      <Text type="secondary">连线 {workflowEdges.length} 条</Text>
    </div>
  );
}
