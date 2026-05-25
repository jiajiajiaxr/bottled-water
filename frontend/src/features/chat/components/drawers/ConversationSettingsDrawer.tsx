import { useEffect, useMemo, useState } from "react";
import {
  BranchesOutlined,
  CheckCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Progress,
  Select,
  Space,
  Tag,
  Tabs,
} from "antd";
import { api } from "../../../../api";
import { mergeConversationCategories } from "../../../../lib/conversation";
import {
  createWorkflowNode,
  WORKFLOW_NODE_TYPE_OPTIONS,
  workflowNodeType,
} from "../../../../lib/workflow";
import { layoutWorkflowPositions } from "../../../../lib/workflowLayout";
import type {
  Agent,
  Conversation,
  ConversationWorkflow,
  McpServer,
  Skill,
  ToolDefinition,
  WorkflowNode,
  WorkflowRun,
} from "../../../../types";
import { WorkflowCanvas } from "./WorkflowCanvas";

const { TextArea } = Input;

export function ConversationSettingsDrawer({
  open,
  active,
  agents,
  categoryOptions,
  onClose,
  onSaveConversation,
}: {
  open: boolean;
  active?: Conversation;
  agents: Agent[];
  categoryOptions: string[];
  onClose: () => void;
  onSaveConversation: (
    conversation: Conversation,
    patch: Partial<Conversation>,
  ) => Promise<void>;
}) {
  const [form] = Form.useForm();
  const [nodeForm] = Form.useForm();
  const [workflow, setWorkflow] = useState<ConversationWorkflow>();
  const [workflowJson, setWorkflowJson] = useState("");
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRun[]>([]);
  const [workflowGenerating, setWorkflowGenerating] = useState(false);
  const [workflowInstruction, setWorkflowInstruction] = useState("");
  const [newNodeType, setNewNodeType] = useState("agent");
  const [editingNodeId, setEditingNodeId] = useState<string>();
  const [toolCatalog, setToolCatalog] = useState<ToolDefinition[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const { message } = AntApp.useApp();
  const conversationCategoryOptions = useMemo(
    () =>
      mergeConversationCategories(categoryOptions, [
        active?.folder || active?.category || "Default",
      ]).map((name) => ({
        label: name,
        value: name,
      })),
    [active?.category, active?.folder, categoryOptions],
  );

  const workflowNodes = workflow?.nodes ?? [];
  const workflowEdges = (workflow?.edges ?? [])
    .map((edge) =>
      Array.isArray(edge)
        ? [String(edge[0] ?? ""), String(edge[1] ?? "")]
        : [
            String(edge.from ?? edge.source ?? ""),
            String(edge.to ?? edge.target ?? ""),
          ],
    )
    .filter(([from, to]) => from && to);
  const activeAgentIds = new Set(
    active?.participants
      .map((item) => item.agent_id)
      .filter(Boolean) as string[],
  );
  const agentOptions = agents
    .filter((agent) => !activeAgentIds.size || activeAgentIds.has(agent.id))
    .map((agent) => ({
      label: `${agent.name} · ${agent.type}`,
      value: agent.id,
    }));
  const toolOptions = Array.from(
    new Set([
      "file.read",
      "file.write",
      "file.extract_text",
      "artifact.create_html",
      ...toolCatalog.map((tool) => tool.name),
    ]),
  ).map((name) => ({ label: name, value: name }));
  const skillOptions = skills.map((skill) => ({
    label: `${skill.name} · ${skill.category}`,
    value: skill.id,
  }));
  const mcpServerOptions = mcpServers.map((server) => ({
    label: `${server.name} · ${server.transport}`,
    value: server.id,
  }));
  const mcpToolOptions = mcpServers.flatMap((server) =>
    (server.tools ?? []).map((tool) => ({
      label: `${server.name} · ${tool.name}`,
      value: tool.name,
    })),
  );
  const editingNode = workflowNodes.find((node) => node.id === editingNodeId);

  const setWorkflowDraft = (next: ConversationWorkflow) => {
    const normalized = layoutWorkflowPositions(next);
    setWorkflow(normalized);
    setWorkflowJson(JSON.stringify(normalized, null, 2));
  };

  const loadWorkflow = async () => {
    if (!active?.id) {
      setWorkflow(undefined);
      setWorkflowJson("");
      setWorkflowRuns([]);
      return;
    }
    const [nextWorkflow, runs, nextTools, nextSkills, nextMcpServers] =
      await Promise.all([
        api.conversationWorkflow(active.id),
        api.workflowRuns(active.id).catch(() => []),
        api.tools(active.workspace_id).catch(() => []),
        api.skills(active.workspace_id).catch(() => []),
        api.mcpServers(active.workspace_id).catch(() => []),
      ]);
    setWorkflowDraft(nextWorkflow);
    setWorkflowInstruction(
      String(nextWorkflow.settings?.generation_instruction ?? ""),
    );
    setWorkflowRuns(runs);
    setToolCatalog(nextTools);
    setSkills(nextSkills);
    setMcpServers(nextMcpServers);
  };

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      title: active?.title,
      folder: active?.folder || active?.category || "Default",
      remark: active?.remark || "",
    });
    loadWorkflow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, active?.id]);

  const addWorkflowNode = (type: string) => {
    if (!workflow || workflowGenerating) return;
    const node = createWorkflowNode(
      type,
      agents.find((agent) => activeAgentIds.has(agent.id)) ?? agents[0],
    );
    const nodes = [...workflow.nodes];
    const endIndex = nodes.findIndex(
      (item) => workflowNodeType(item) === "end",
    );
    const insertIndex = endIndex >= 0 ? endIndex : nodes.length;
    nodes.splice(insertIndex, 0, node);
    const previous = nodes[Math.max(0, insertIndex - 1)];
    const next = nodes[insertIndex + 1];
    const edges = [...(workflow.edges ?? [])];
    if (previous && previous.id !== node.id) edges.push([previous.id, node.id]);
    if (next) edges.push([node.id, next.id]);
    setWorkflowDraft({ ...workflow, nodes, edges });
    setEditingNodeId(node.id);
    nodeForm.setFieldsValue({
      title: node.title,
      type: node.type,
      agent_id: node.agent_id,
      tool_name: node.config?.tool_name,
      skill_id: node.config?.skill_id,
      mcp_server_id: node.config?.server_id,
      mcp_tool_name: node.config?.tool_name,
      expression: node.config?.expression,
      max_iterations: node.config?.max_iterations,
      artifact_type: node.config?.artifact_type,
      meta: node.meta,
    });
  };

  const openWorkflowNodeEditor = (node: WorkflowNode) => {
    if (workflowGenerating) return;
    const config = node.config ?? {};
    setEditingNodeId(node.id);
    nodeForm.setFieldsValue({
      title: node.title,
      type: workflowNodeType(node),
      agent_id: node.agent_id ?? config.agent_id,
      tool_name: config.tool_name,
      skill_id: config.skill_id,
      mcp_server_id: config.server_id,
      mcp_tool_name: config.tool_name,
      expression: config.expression,
      max_iterations: config.max_iterations ?? 3,
      artifact_type: config.artifact_type ?? "html",
      meta: node.meta,
    });
  };

  const saveWorkflowNode = async () => {
    if (!workflow || !editingNodeId || workflowGenerating) return;
    const values = await nodeForm.validateFields();
    const type = values.type;
    const config: Record<string, unknown> = {};
    if (type === "agent" || type === "review")
      config.agent_id = values.agent_id;
    if (type === "tool") config.tool_name = values.tool_name;
    if (type === "skill") config.skill_id = values.skill_id;
    if (type === "mcp") {
      config.server_id = values.mcp_server_id;
      config.tool_name = values.mcp_tool_name;
    }
    if (type === "condition") {
      config.expression = values.expression || "true";
      config.branches = ["true", "false"];
    }
    if (type === "loop")
      config.max_iterations = Number(values.max_iterations || 3);
    if (type === "artifact")
      config.artifact_type = values.artifact_type || "html";
    const nodes = workflow.nodes.map((node) =>
      node.id === editingNodeId
        ? {
            ...node,
            title: values.title,
            type,
            role: type === "review" ? "reviewer" : type,
            agent_id: config.agent_id ? String(config.agent_id) : undefined,
            config,
            meta: values.meta || node.meta,
          }
        : node,
    );
    setWorkflowDraft({ ...workflow, nodes });
    setEditingNodeId(undefined);
  };

  const saveWorkflow = async () => {
    if (!active || workflowGenerating) return;
    let parsed: ConversationWorkflow;
    try {
      parsed = layoutWorkflowPositions(
        JSON.parse(workflowJson) as ConversationWorkflow,
      );
    } catch {
      message.error("工作流 JSON 格式不正确");
      return;
    }
    const saved = await api.saveConversationWorkflow(active.id, parsed);
    setWorkflowDraft(saved);
    message.success("群聊工作流已保存");
  };

  return (
    <Drawer title="群聊设置" width={980} open={open} onClose={onClose}>
      <Tabs
        items={[
          {
            key: "base",
            label: "基本信息",
            children: (
              <Form
                form={form}
                layout="vertical"
                onFinish={async (values) => {
                  if (!active) return;
                  await onSaveConversation(active, {
                    title: values.title,
                    folder: values.folder,
                    category: values.folder,
                    remark: values.remark,
                  });
                  message.success("群聊信息已保存");
                }}
              >
                <Form.Item
                  name="title"
                  label="群聊名称"
                  rules={[{ required: true }]}
                >
                  <Input maxLength={80} />
                </Form.Item>
                <Form.Item name="folder" label="分类/文件夹">
                  <Select
                    options={conversationCategoryOptions}
                    placeholder="选择分类"
                  />
                </Form.Item>
                <Form.Item name="remark" label="备注">
                  <TextArea rows={3} maxLength={300} />
                </Form.Item>
                <Button type="primary" htmlType="submit" disabled={!active}>
                  保存信息
                </Button>
              </Form>
            ),
          },
          {
            key: "workflow",
            label: "工作流画布",
            children: (
              <div className="workflow-board conversation-workflow">
                <div className="workflow-canvas">
                  {workflow ? (
                    <WorkflowCanvas
                      workflow={workflow}
                      latestRun={workflowRuns[0]}
                      locked={workflowGenerating}
                      overlayText={
                        workflowGenerating ? "AI 正在生成工作流…" : undefined
                      }
                      onChange={setWorkflowDraft}
                      onNodeClick={openWorkflowNodeEditor}
                    />
                  ) : (
                    <Empty description="当前群聊暂无工作流" />
                  )}
                </div>
                <div className="workflow-side">
                  <Space direction="vertical" className="full-width">
                    <Space wrap>
                      <Button
                        icon={<ReloadOutlined />}
                        disabled={!active || workflowGenerating}
                        onClick={loadWorkflow}
                      >
                        重新载入
                      </Button>
                      <Button
                        icon={<RobotOutlined />}
                        loading={workflowGenerating}
                        disabled={!active}
                        onClick={async () => {
                          if (!active || workflowGenerating) return;
                          setEditingNodeId(undefined);
                          setWorkflowGenerating(true);
                          try {
                            const generated =
                              await api.generateConversationWorkflow(
                                active.id,
                                workflowInstruction,
                              );
                            setWorkflowDraft(generated);
                            message.success("AI 已生成工作流");
                          } catch (error) {
                            message.error(
                              error instanceof Error
                                ? error.message
                                : "AI 生成工作流失败",
                            );
                          } finally {
                            setWorkflowGenerating(false);
                          }
                        }}
                      >
                        AI 生成
                      </Button>
                      <Button
                        icon={<PlusOutlined />}
                        disabled={!workflow || workflowGenerating}
                        onClick={() => addWorkflowNode(newNodeType)}
                      >
                        添加节点
                      </Button>
                      <Button
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        disabled={!workflowJson.trim() || workflowGenerating}
                        onClick={saveWorkflow}
                      >
                        保存画布
                      </Button>
                      <Button
                        icon={<BranchesOutlined />}
                        disabled={!active || !workflow || workflowGenerating}
                        onClick={async () => {
                          if (!active || !workflow || workflowGenerating) return;
                          const run = await api.startWorkflowRun(
                            active.id,
                            workflow,
                          );
                          setWorkflowRuns((current) => [run, ...current]);
                          message.success("工作流运行已创建");
                        }}
                      >
                        运行
                      </Button>
                    </Space>
                    <TextArea
                      rows={3}
                      value={workflowInstruction}
                      disabled={workflowGenerating}
                      onChange={(event) =>
                        setWorkflowInstruction(event.target.value)
                      }
                      placeholder="给 AI 的画布编排意见，例如：前后端并行，Reviewer 最后审查；这个群聊只做日常问答时跳过 Master。"
                    />
                    <Select
                      value={newNodeType}
                      onChange={setNewNodeType}
                      options={WORKFLOW_NODE_TYPE_OPTIONS}
                      disabled={workflowGenerating}
                      className="full-width"
                    />
                    <Select
                      value={workflow?.output_mode ?? "independent_messages"}
                      disabled={!workflow || workflowGenerating}
                      onChange={(value) => {
                        if (!workflow) return;
                        setWorkflowDraft({ ...workflow, output_mode: value });
                      }}
                      options={[
                        { label: "独立气泡回复", value: "independent_messages" },
                        { label: "汇总回复", value: "aggregate" },
                      ]}
                      className="full-width"
                    />
                    <TextArea
                      rows={12}
                      value={workflowJson}
                      disabled={workflowGenerating}
                      onChange={(event) => setWorkflowJson(event.target.value)}
                    />
                    <Card title="连线与运行态">
                      <Space direction="vertical" className="full-width">
                        <Space size={[4, 4]} wrap>
                          {workflowEdges.length ? (
                            workflowEdges.map(([from, to]) => (
                              <Tag key={`${from}-${to}`}>
                                {from} → {to}
                              </Tag>
                            ))
                          ) : (
                            <Tag>默认并行独立回复</Tag>
                          )}
                        </Space>
                        {workflowRuns[0] && (
                          <Progress
                            percent={workflowRuns[0].progress}
                            status={
                              workflowRuns[0].status === "failed"
                                ? "exception"
                                : "active"
                            }
                          />
                        )}
                      </Space>
                    </Card>
                  </Space>
                </div>
              </div>
            ),
          },
        ]}
      />
      <Modal
        title="编辑工作流节点"
        open={Boolean(editingNode) && !workflowGenerating}
        onCancel={() => setEditingNodeId(undefined)}
        onOk={saveWorkflowNode}
        confirmLoading={workflowGenerating}
        okText="保存节点"
      >
        <Form form={nodeForm} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input maxLength={80} />
          </Form.Item>
          <Form.Item name="type" label="节点类型" rules={[{ required: true }]}>
            <Select
              options={[
                { label: "Start", value: "start" },
                ...WORKFLOW_NODE_TYPE_OPTIONS,
                { label: "Skill", value: "skill" },
                { label: "MCP", value: "mcp" },
                { label: "End", value: "end" },
              ]}
            />
          </Form.Item>
          <Form.Item shouldUpdate noStyle>
            {({ getFieldValue }) => {
              const type = getFieldValue("type");
              return (
                <>
                  {(type === "agent" || type === "review") && (
                    <Form.Item name="agent_id" label="Agent">
                      <Select
                        allowClear
                        options={agentOptions}
                        placeholder="选择群聊内 Agent"
                      />
                    </Form.Item>
                  )}
                  {type === "tool" && (
                    <Form.Item name="tool_name" label="工具名">
                      <Select
                        showSearch
                        options={toolOptions}
                        placeholder="file.read / artifact.create_html"
                      />
                    </Form.Item>
                  )}
                  {type === "skill" && (
                    <Form.Item name="skill_id" label="Skill">
                      <Select
                        showSearch
                        options={skillOptions}
                        placeholder="选择 Skill"
                      />
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
                      <TextArea
                        rows={2}
                        placeholder="input.includes('需要审查')"
                      />
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
                        options={["html", "pdf", "docx", "xlsx", "pptx"].map(
                          (value) => ({ label: value, value }),
                        )}
                      />
                    </Form.Item>
                  )}
                </>
              );
            }}
          </Form.Item>
          <Form.Item name="meta" label="说明">
            <TextArea rows={3} maxLength={160} />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
}
