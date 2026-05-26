import { useEffect, useMemo, useState } from "react";
import {
  CheckCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Progress,
  Select,
  Space,
  Tag,
  Tabs,
  Typography,
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

const { Text } = Typography;
const { TextArea } = Input;
type WorkflowEdge = ConversationWorkflow["edges"][number];

function edgeSource(edge: WorkflowEdge): string {
  return Array.isArray(edge)
    ? String(edge[0])
    : String(edge.from ?? edge.source ?? "");
}

function edgeTarget(edge: WorkflowEdge): string {
  return Array.isArray(edge)
    ? String(edge[1])
    : String(edge.to ?? edge.target ?? "");
}

function edgeCondition(edge: WorkflowEdge): string | undefined {
  return Array.isArray(edge) ? undefined : edge.condition;
}

function edgeId(edge: WorkflowEdge): string {
  return `${edgeSource(edge)}-${edgeTarget(edge)}-${edgeCondition(edge) ?? "edge"}`;
}

function textFromConfigValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function configValueFromText(value?: string) {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return undefined;
  try {
    return JSON.parse(trimmed) as unknown;
  } catch {
    return trimmed;
  }
}

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
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);
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
    .map((edge) => [edgeSource(edge), edgeTarget(edge)])
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
  const latestWorkflowRun = workflowRuns[0];
  const latestWorkflowRunId = latestWorkflowRun?.id;
  const latestWorkflowRunStatus = latestWorkflowRun?.status;
  const editingNode = workflowNodes.find((node) => node.id === editingNodeId);
  const editingNodeState = latestWorkflowRun?.node_states?.find(
    (state) => state.id === editingNodeId,
  );

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
      setSelectedNodeIds([]);
      setSelectedEdgeIds([]);
      setEditingNodeId(undefined);
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

  useEffect(() => {
    if (!open || !active?.id) return;
    if (
      !latestWorkflowRunStatus ||
      !["running", "queued"].includes(latestWorkflowRunStatus)
    )
      return;
    const timer = window.setInterval(() => {
      api
        .workflowRuns(active.id)
        .then(setWorkflowRuns)
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [open, active?.id, latestWorkflowRunId, latestWorkflowRunStatus]);

  const hydrateNodeForm = (node: WorkflowNode) => {
    const config = node.config ?? {};
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
      failure_strategy: config.failure_strategy ?? "stop",
      retry: Number(config.retry ?? config.retry_count ?? 0),
      input_mapping: textFromConfigValue(config.input ?? config.inputs),
      output_mapping: textFromConfigValue(config.output ?? config.outputs),
      meta: node.meta,
    });
  };

  const addWorkflowNode = (type: string) => {
    if (!workflow || workflowGenerating) return;
    const node = createWorkflowNode(
      type,
      agents.find((agent) => activeAgentIds.has(agent.id)) ?? agents[0],
    );
    const nodes = [...workflow.nodes];
    const selectedNode = nodes.find((item) => item.id === editingNodeId);
    const anchor = selectedNode ?? nodes[nodes.length - 1];
    node.position = {
      x: (anchor?.position?.x ?? 48) + 300,
      y: selectedNode ? anchor?.position?.y ?? 64 : 80 + nodes.length * 36,
    };
    const endIndex = nodes.findIndex((item) => workflowNodeType(item) === "end");
    const insertIndex = endIndex >= 0 ? endIndex : nodes.length;
    nodes.splice(insertIndex, 0, node);
    const edges = [...(workflow.edges ?? [])];
    if (selectedNode && workflowNodeType(selectedNode) !== "end") {
      edges.push([selectedNode.id, node.id]);
    } else {
      const previous = nodes[Math.max(0, insertIndex - 1)];
      const next = nodes[insertIndex + 1];
      if (previous && previous.id !== node.id) edges.push([previous.id, node.id]);
      if (next) edges.push([node.id, next.id]);
    }
    setWorkflowDraft({ ...workflow, nodes, edges });
    setSelectedNodeIds([node.id]);
    setSelectedEdgeIds([]);
    setEditingNodeId(node.id);
    hydrateNodeForm(node);
  };

  const openWorkflowNodeEditor = (node: WorkflowNode) => {
    if (workflowGenerating) return;
    setSelectedNodeIds([node.id]);
    setSelectedEdgeIds([]);
    setEditingNodeId(node.id);
    hydrateNodeForm(node);
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
    const input = configValueFromText(values.input_mapping);
    const output = configValueFromText(values.output_mapping);
    if (input !== undefined) config.input = input;
    if (output !== undefined) config.output = output;
    config.failure_strategy = values.failure_strategy || "stop";
    config.retry = Number(values.retry || 0);
    const nodes = workflow.nodes.map((node) =>
      node.id === editingNodeId
        ? {
            ...node,
            title: values.title,
            type,
            role: type === "review" ? "reviewer" : type,
            agent_id: config.agent_id ? String(config.agent_id) : undefined,
            data: {
              ...(node.data ?? {}),
              title: values.title,
              description: values.meta || "",
              input,
              output,
            },
            config,
            meta: values.meta || node.meta,
          }
        : node,
    );
    setWorkflowDraft({ ...workflow, nodes });
    setSelectedNodeIds([editingNodeId]);
    setSelectedEdgeIds([]);
  };

  const deleteSelection = () => {
    if (!workflow || workflowGenerating) return;
    const protectedIds = new Set(
      workflow.nodes
        .filter((node) => ["start", "end"].includes(workflowNodeType(node)))
        .map((node) => node.id),
    );
    const removableNodeIds = new Set(
      selectedNodeIds.filter((id) => !protectedIds.has(id)),
    );
    const edgeIds = new Set(selectedEdgeIds);
    if (!removableNodeIds.size && !edgeIds.size) {
      message.info("请选择可删除的节点或连线");
      return;
    }
    const nodes = workflow.nodes.filter((node) => !removableNodeIds.has(node.id));
    const edges = (workflow.edges ?? []).filter((edge) => {
      if (edgeIds.has(edgeId(edge))) return false;
      return (
        !removableNodeIds.has(edgeSource(edge)) &&
        !removableNodeIds.has(edgeTarget(edge))
      );
    });
    setWorkflowDraft({ ...workflow, nodes, edges });
    setSelectedNodeIds([]);
    setSelectedEdgeIds([]);
    setEditingNodeId(undefined);
  };

  const copySelection = () => {
    if (!workflow || workflowGenerating) return;
    const sourceIds = new Set(
      selectedNodeIds.filter((id) => {
        const node = workflow.nodes.find((item) => item.id === id);
        return node && !["start", "end"].includes(workflowNodeType(node));
      }),
    );
    if (!sourceIds.size) {
      message.info("请选择要复制的业务节点");
      return;
    }
    const idMap = new Map<string, string>();
    const now = Date.now().toString(36);
    const clonedNodes = workflow.nodes
      .filter((node) => sourceIds.has(node.id))
      .map((node, index) => {
        const type = workflowNodeType(node);
        const nextId = `${type}-${now}-${index}`;
        idMap.set(node.id, nextId);
        return {
          ...node,
          id: nextId,
          title: `${node.title} Copy`,
          status: "ready",
          position: {
            x: (node.position?.x ?? 48) + 36,
            y: (node.position?.y ?? 64) + 36,
          },
          data: { ...(node.data ?? {}), copied_from: node.id },
        };
      });
    const clonedEdges = (workflow.edges ?? [])
      .filter(
        (edge) => sourceIds.has(edgeSource(edge)) && sourceIds.has(edgeTarget(edge)),
      )
      .map((edge) => {
        const from = idMap.get(edgeSource(edge))!;
        const to = idMap.get(edgeTarget(edge))!;
        return Array.isArray(edge)
          ? [from, to]
          : {
              ...edge,
              from,
              source: from,
              to,
              target: to,
            };
      });
    setWorkflowDraft({
      ...workflow,
      nodes: [...workflow.nodes, ...clonedNodes],
      edges: [...(workflow.edges ?? []), ...clonedEdges],
    });
    setSelectedNodeIds(clonedNodes.map((node) => node.id));
    setSelectedEdgeIds([]);
    setEditingNodeId(clonedNodes[0]?.id);
    if (clonedNodes[0]) hydrateNodeForm(clonedNodes[0]);
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
    <Drawer title="群聊设置" width={1280} open={open} onClose={onClose}>
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
                      latestRun={latestWorkflowRun}
                      locked={workflowGenerating}
                      overlayText={
                        workflowGenerating ? "AI 正在生成工作流…" : undefined
                      }
                      selectedNodeIds={selectedNodeIds}
                      selectedEdgeIds={selectedEdgeIds}
                      onChange={setWorkflowDraft}
                      onNodeClick={openWorkflowNodeEditor}
                      onPaneClick={() => {
                        setSelectedNodeIds([]);
                        setSelectedEdgeIds([]);
                        setEditingNodeId(undefined);
                      }}
                      onCopySelection={copySelection}
                      onSelectionChange={(nodeIds, edgeIds) => {
                        setSelectedNodeIds(nodeIds);
                        setSelectedEdgeIds(edgeIds);
                        if (nodeIds.length === 1) {
                          const node = workflow.nodes.find(
                            (item) => item.id === nodeIds[0],
                          );
                          if (node) {
                            setEditingNodeId(node.id);
                            hydrateNodeForm(node);
                          }
                        } else if (nodeIds.length > 1 || edgeIds.length) {
                          setEditingNodeId(undefined);
                        }
                      }}
                    />
                  ) : (
                    <Empty description="当前群聊暂无工作流" />
                  )}
                </div>
                <div className="workflow-side">
                  <Space direction="vertical" className="full-width">
                    <div className="workflow-panel">
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
                          type="primary"
                          icon={<SaveOutlined />}
                          disabled={!workflowJson.trim() || workflowGenerating}
                          onClick={saveWorkflow}
                        >
                          保存画布
                        </Button>
                        <Button
                          icon={<PlayCircleOutlined />}
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
                    </div>

                    <div className="workflow-panel">
                      <Text strong>节点工具</Text>
                      <Select
                        value={newNodeType}
                        onChange={setNewNodeType}
                        options={[
                          { label: "Start", value: "start" },
                          ...WORKFLOW_NODE_TYPE_OPTIONS,
                          { label: "End", value: "end" },
                        ]}
                        disabled={workflowGenerating}
                        className="full-width"
                      />
                      <Space wrap>
                        <Button
                          icon={<PlusOutlined />}
                          disabled={!workflow || workflowGenerating}
                          onClick={() => addWorkflowNode(newNodeType)}
                        >
                          新增
                        </Button>
                        <Button
                          icon={<CopyOutlined />}
                          disabled={!selectedNodeIds.length || workflowGenerating}
                          onClick={copySelection}
                        >
                          复制
                        </Button>
                        <Button
                          danger
                          icon={<DeleteOutlined />}
                          disabled={
                            (!selectedNodeIds.length && !selectedEdgeIds.length) ||
                            workflowGenerating
                          }
                          onClick={deleteSelection}
                        >
                          删除
                        </Button>
                      </Space>
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
                    </div>

                    <div className="workflow-panel workflow-node-config">
                      <Space direction="vertical" className="full-width">
                        <Space align="center" wrap>
                          <Text strong>节点配置</Text>
                          {editingNode && (
                            <Tag color="processing">
                              {editingNodeState?.status ||
                                editingNode.status ||
                                "queued"}
                            </Tag>
                          )}
                        </Space>
                        {editingNode ? (
                          <Form form={nodeForm} layout="vertical">
                            <Form.Item
                              name="title"
                              label="名称"
                              rules={[{ required: true }]}
                            >
                              <Input maxLength={80} disabled={workflowGenerating} />
                            </Form.Item>
                            <Form.Item
                              name="type"
                              label="节点类型"
                              rules={[{ required: true }]}
                            >
                              <Select
                                disabled={workflowGenerating}
                                options={[
                                  { label: "Start", value: "start" },
                                  ...WORKFLOW_NODE_TYPE_OPTIONS,
                                  { label: "End", value: "end" },
                                ]}
                              />
                            </Form.Item>
                            <Form.Item name="meta" label="说明">
                              <TextArea
                                rows={2}
                                maxLength={300}
                                disabled={workflowGenerating}
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
                                          showSearch
                                          disabled={workflowGenerating}
                                          options={agentOptions}
                                          placeholder="选择群聊内 Agent"
                                        />
                                      </Form.Item>
                                    )}
                                    {type === "tool" && (
                                      <Form.Item name="tool_name" label="工具">
                                        <Select
                                          showSearch
                                          disabled={workflowGenerating}
                                          options={toolOptions}
                                          placeholder="file.read / artifact.create_html"
                                        />
                                      </Form.Item>
                                    )}
                                    {type === "skill" && (
                                      <Form.Item name="skill_id" label="Skill">
                                        <Select
                                          showSearch
                                          disabled={workflowGenerating}
                                          options={skillOptions}
                                          placeholder="选择 Skill"
                                        />
                                      </Form.Item>
                                    )}
                                    {type === "mcp" && (
                                      <>
                                        <Form.Item name="mcp_server_id" label="MCP Server">
                                          <Select
                                            allowClear
                                            disabled={workflowGenerating}
                                            options={mcpServerOptions}
                                          />
                                        </Form.Item>
                                        <Form.Item name="mcp_tool_name" label="MCP Tool">
                                          <Select
                                            showSearch
                                            disabled={workflowGenerating}
                                            options={mcpToolOptions}
                                          />
                                        </Form.Item>
                                      </>
                                    )}
                                    {type === "condition" && (
                                      <Form.Item name="expression" label="条件表达式">
                                        <TextArea
                                          rows={2}
                                          disabled={workflowGenerating}
                                          placeholder="input.includes('需要审查')"
                                        />
                                      </Form.Item>
                                    )}
                                    {type === "loop" && (
                                      <Form.Item name="max_iterations" label="循环次数">
                                        <Input
                                          type="number"
                                          min={1}
                                          max={20}
                                          disabled={workflowGenerating}
                                        />
                                      </Form.Item>
                                    )}
                                    {type === "artifact" && (
                                      <Form.Item name="artifact_type" label="产物类型">
                                        <Select
                                          disabled={workflowGenerating}
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
                            <Form.Item name="input_mapping" label="输入">
                              <TextArea
                                rows={3}
                                disabled={workflowGenerating}
                                placeholder='例如 {"prompt": "$input", "context": "$node.backend.output"}'
                              />
                            </Form.Item>
                            <Form.Item name="output_mapping" label="输出">
                              <TextArea
                                rows={3}
                                disabled={workflowGenerating}
                                placeholder='例如 {"summary": "$result.text"}'
                              />
                            </Form.Item>
                            <Space wrap>
                              <Form.Item
                                name="failure_strategy"
                                label="失败策略"
                                className="workflow-inline-form-item"
                              >
                                <Select
                                  disabled={workflowGenerating}
                                  options={[
                                    { label: "停止后续", value: "stop" },
                                    { label: "跳过继续", value: "continue" },
                                    { label: "重试", value: "retry" },
                                  ]}
                                />
                              </Form.Item>
                              <Form.Item
                                name="retry"
                                label="重试次数"
                                className="workflow-inline-form-item"
                              >
                                <Input
                                  type="number"
                                  min={0}
                                  max={3}
                                  disabled={workflowGenerating}
                                />
                              </Form.Item>
                            </Space>
                            <Button
                              type="primary"
                              icon={<CheckCircleOutlined />}
                              disabled={workflowGenerating}
                              onClick={saveWorkflowNode}
                            >
                              应用配置
                            </Button>
                          </Form>
                        ) : (
                          <Empty
                            image={Empty.PRESENTED_IMAGE_SIMPLE}
                            description="点击画布节点后在这里配置"
                          />
                        )}
                      </Space>
                    </div>

                    <div className="workflow-panel">
                      <Space direction="vertical" className="full-width">
                        <Text strong>运行态</Text>
                        {latestWorkflowRun ? (
                          <>
                            <Space wrap>
                              <Tag>{latestWorkflowRun.status}</Tag>
                              <Text type="secondary">
                                {latestWorkflowRun.progress}% complete
                              </Text>
                            </Space>
                            <Progress
                              percent={latestWorkflowRun.progress}
                              status={
                                latestWorkflowRun.status === "failed"
                                  ? "exception"
                                  : latestWorkflowRun.status === "completed"
                                    ? "success"
                                    : "active"
                              }
                            />
                          </>
                        ) : (
                          <Text type="secondary">暂无运行记录</Text>
                        )}
                        <Space size={[4, 4]} wrap>
                          {workflowEdges.length ? (
                            workflowEdges.map(([from, to]) => (
                              <Tag key={`${from}-${to}`}>
                                {from} → {to}
                              </Tag>
                            ))
                          ) : (
                            <Tag>暂无连线</Tag>
                          )}
                        </Space>
                      </Space>
                    </div>

                    <div className="workflow-panel">
                      <Text strong>Workflow JSON</Text>
                      <TextArea
                        rows={8}
                        value={workflowJson}
                        disabled={workflowGenerating}
                        onChange={(event) => setWorkflowJson(event.target.value)}
                      />
                    </div>
                  </Space>
                </div>
              </div>
            ),
          },
        ]}
      />
    </Drawer>
  );
}
