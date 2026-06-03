import { useEffect, useMemo, useState } from "react";
import type { FormInstance } from "antd";
import { api } from "../../api";
import {
  createWorkflowNode,
  workflowNodeType,
} from "../../lib/workflow";
import { layoutWorkflowPositions } from "../../lib/workflowLayout";
import type {
  Agent,
  Conversation,
  ConversationWorkflow,
  McpServer,
  Skill,
  ToolDefinition,
  WorkflowNode,
  WorkflowRun,
} from "../../types";
import {
  configValueFromText,
  edgeId,
  edgeSource,
  edgeTarget,
  textFromConfigValue,
} from "./utils";

export function useWorkflowStudio({
  workspaceId,
  conversationId,
  nodeForm,
  onError,
}: {
  workspaceId: string;
  conversationId: string;
  nodeForm: FormInstance;
  onError: (message: string) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [conversation, setConversation] = useState<Conversation>();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [workflow, setWorkflow] = useState<ConversationWorkflow>();
  const [workflowJson, setWorkflowJson] = useState("");
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRun[]>([]);
  const [toolCatalog, setToolCatalog] = useState<ToolDefinition[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [workflowGenerating, setWorkflowGenerating] = useState(false);
  const [workflowInstruction, setWorkflowInstruction] = useState("");
  const [newNodeType, setNewNodeType] = useState("agent");
  const [editingNodeId, setEditingNodeId] = useState<string>();
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);

  const latestRun = workflowRuns[0];
  const latestRunId = latestRun?.id;
  const latestRunStatus = latestRun?.status;
  const workflowNodes = workflow?.nodes ?? [];
  const editingNode = workflowNodes.find((node) => node.id === editingNodeId);
  const editingNodeState = latestRun?.node_states?.find(
    (state) => state.id === editingNodeId,
  );
  const activeAgentIds = new Set(
    conversation?.participants
      .map((item) => item.agent_id)
      .filter((id): id is string => Boolean(id)) ?? [],
  );
  const activeAgents = agents.filter((agent) => activeAgentIds.has(agent.id));
  const nodeStateById = useMemo(
    () => new Map((latestRun?.node_states ?? []).map((node) => [node.id, node])),
    [latestRun],
  );
  const workflowEdges = (workflow?.edges ?? [])
    .map((edge) => [edgeSource(edge), edgeTarget(edge)])
    .filter(([from, to]) => from && to);

  const agentOptions = agents.map((agent) => ({
    label: activeAgentIds.has(agent.id)
      ? `${agent.name} · ${agent.type}`
      : `${agent.name} · ${agent.type} (未加入)`,
    value: agent.id,
  }));
  const toolOptions = Array.from(
    new Set([
      "file.read",
      "file.write",
      "file.extract_text",
      "artifact.create_html",
      "artifact.create_docx",
      "artifact.create_pdf",
      "sandbox.run",
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

  const setWorkflowDraft = (next: ConversationWorkflow) => {
    const normalized = layoutWorkflowPositions(next);
    setWorkflow(normalized);
    setWorkflowJson(JSON.stringify(normalized, null, 2));
  };

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

  const loadWorkflow = async () => {
    if (!workspaceId || !conversationId) return;
    setLoading(true);
    try {
      const [
        nextConversations,
        nextAgents,
        nextWorkflow,
        runs,
        nextTools,
        nextSkills,
        nextMcpServers,
      ] = await Promise.all([
        api.conversations(workspaceId),
        api.agents(),
        api.conversationWorkflow(conversationId),
        api.workflowRuns(conversationId).catch(() => []),
        api.tools(workspaceId).catch(() => []),
        api.skills(workspaceId).catch(() => []),
        api.mcpServers(workspaceId).catch(() => []),
      ]);
      setConversation(nextConversations.find((item) => item.id === conversationId));
      setAgents(nextAgents);
      setWorkflowDraft(nextWorkflow);
      setWorkflowRuns(runs);
      setToolCatalog(nextTools);
      setSkills(nextSkills);
      setMcpServers(nextMcpServers);
      setWorkflowInstruction(
        String(nextWorkflow.settings?.generation_instruction ?? ""),
      );
      setSelectedNodeIds([]);
      setSelectedEdgeIds([]);
      setEditingNodeId(undefined);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!workspaceId || !conversationId) return;
    loadWorkflow().catch((error) => {
      onError(error instanceof Error ? error.message : "工作流加载失败");
      setLoading(false);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId, conversationId]);

  useEffect(() => {
    if (!latestRunStatus || !["running", "queued"].includes(latestRunStatus)) return;
    const timer = window.setInterval(() => {
      api.workflowRuns(conversationId).then(setWorkflowRuns).catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [conversationId, latestRunId, latestRunStatus]);

  const openNodeEditor = (node: WorkflowNode) => {
    if (workflowGenerating) return;
    setSelectedNodeIds([node.id]);
    setSelectedEdgeIds([]);
    setEditingNodeId(node.id);
    hydrateNodeForm(node);
  };

  const addWorkflowNode = (
    type: string,
    position?: { x: number; y: number },
  ) => {
    if (!workflow || workflowGenerating) return;
    const node = createWorkflowNode(type, activeAgents[0] ?? agents[0]);
    const nodes = [...workflow.nodes];
    const selectedNode = nodes.find((item) => item.id === editingNodeId);
    const anchor = selectedNode ?? nodes[nodes.length - 1];
    node.position =
      position ?? {
        x: (anchor?.position?.x ?? 48) + 300,
        y: selectedNode ? anchor?.position?.y ?? 64 : 80 + nodes.length * 36,
      };
    const endIndex = nodes.findIndex((item) => workflowNodeType(item) === "end");
    nodes.splice(endIndex >= 0 ? endIndex : nodes.length, 0, node);
    const edges = [...(workflow.edges ?? [])];
    if (selectedNode && workflowNodeType(selectedNode) !== "end") {
      edges.push([selectedNode.id, node.id]);
    }
    setWorkflowDraft({ ...workflow, nodes, edges });
    openNodeEditor(node);
  };

  const saveWorkflowNode = async () => {
    if (!workflow || !editingNodeId || workflowGenerating) return;
    const values = await nodeForm.validateFields();
    const type = values.type;
    const config: Record<string, unknown> = {};
    if (type === "agent" || type === "review") config.agent_id = values.agent_id;
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
    if (type === "loop") config.max_iterations = Number(values.max_iterations || 3);
    if (type === "artifact") config.artifact_type = values.artifact_type || "html";
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
            data: { ...(node.data ?? {}), title: values.title, input, output },
            config,
            meta: values.meta || node.meta,
          }
        : node,
    );
    setWorkflowDraft({ ...workflow, nodes });
    setSelectedNodeIds([editingNodeId]);
    setSelectedEdgeIds([]);

    // 自动添加不在 conversation 中的 agent
    const newAgentId = config.agent_id ? String(config.agent_id) : undefined;
    if (newAgentId && conversation && !activeAgentIds.has(newAgentId)) {
      try {
        await api.addParticipants(conversationId, [newAgentId]);
        const nextConversations = await api.conversations(workspaceId);
        setConversation(nextConversations.find((item) => item.id === conversationId));
      } catch {
        // 静默失败，不影响节点保存
      }
    }
  };

  const syncAgentsAfterNodeRemoval = async (
    removedAgentIds: string[],
    currentNodes: WorkflowNode[],
  ) => {
    if (!conversation) return;
    const remainingAgentIds = new Set(
      currentNodes
        .filter((node) => ["agent", "review"].includes(workflowNodeType(node)))
        .map((node) => node.agent_id)
        .filter((id): id is string => Boolean(id)),
    );
    for (const agentId of removedAgentIds) {
      if (remainingAgentIds.has(agentId)) continue;
      const participant = conversation.participants.find(
        (p) => p.agent_id === agentId && p.participant_type === "agent" && !p.left_at,
      );
      if (!participant?.id) continue;
      const remainingAgents = conversation.participants.filter(
        (p) => p.participant_type === "agent" && !p.left_at && p.agent_id !== agentId,
      );
      if (remainingAgents.length < 1) {
        onError("会话至少需要保留 1 个 Agent");
        continue;
      }
      try {
        await api.removeParticipant(conversationId, participant.id);
      } catch {
        onError("同步移除工作流成员失败");
      }
    }
    try {
      const nextConversations = await api.conversations(workspaceId);
      setConversation(nextConversations.find((item) => item.id === conversationId));
    } catch {
      onError("刷新会话列表失败");
    }
  };

  const deleteSelection = async () => {
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
    const removedAgentIds = new Set<string>();
    for (const nodeId of removableNodeIds) {
      const node = workflow.nodes.find((item) => item.id === nodeId);
      if (node && ["agent", "review"].includes(workflowNodeType(node)) && node.agent_id) {
        removedAgentIds.add(node.agent_id);
      }
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
    if (removedAgentIds.size > 0) {
      await syncAgentsAfterNodeRemoval(Array.from(removedAgentIds), nodes);
    }
  };

  const copySelection = () => {
    if (!workflow || workflowGenerating) return;
    const sourceIds = new Set(
      selectedNodeIds.filter((id) => {
        const node = workflow.nodes.find((item) => item.id === id);
        return node && !["start", "end"].includes(workflowNodeType(node));
      }),
    );
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
          : { ...edge, from, source: from, to, target: to };
      });
    setWorkflowDraft({
      ...workflow,
      nodes: [...workflow.nodes, ...clonedNodes],
      edges: [...(workflow.edges ?? []), ...clonedEdges],
    });
    if (clonedNodes[0]) openNodeEditor(clonedNodes[0]);
  };

  return {
    loading,
    conversation,
    workflow,
    setWorkflowDraft,
    workflowJson,
    setWorkflowJson,
    workflowRuns,
    setWorkflowRuns,
    latestRun,
    nodeStateById,
    workflowEdges,
    workflowGenerating,
    setWorkflowGenerating,
    workflowInstruction,
    setWorkflowInstruction,
    newNodeType,
    setNewNodeType,
    selectedNodeIds,
    setSelectedNodeIds,
    selectedEdgeIds,
    setSelectedEdgeIds,
    editingNode,
    editingNodeState,
    setEditingNodeId,
    agentOptions,
    toolOptions,
    skillOptions,
    mcpServerOptions,
    mcpToolOptions,
    loadWorkflow,
    openNodeEditor,
    addWorkflowNode,
    saveWorkflowNode,
    deleteSelection,
    copySelection,
    syncAgentsAfterNodeRemoval,
  };
}
