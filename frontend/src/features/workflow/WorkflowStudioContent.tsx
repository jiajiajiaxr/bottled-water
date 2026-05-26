import { Form, Spin } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import { layoutWorkflowPositions } from "../../lib/workflowLayout";
import { conversationRoutePath } from "../../lib/workflowRoutes";
import type { ConversationWorkflow } from "../../types";
import { workflowSettings } from "./utils";
import { useWorkflowStudio } from "./useWorkflowStudio";
import { WorkflowCanvasPanel } from "./WorkflowCanvasPanel";
import { WorkflowModeToolbar } from "./WorkflowModeToolbar";
import { WorkflowNodeConfigPanel } from "./WorkflowNodeConfigPanel";
import { WorkflowNodePalette } from "./WorkflowNodePalette";
import { WorkflowStudioHeader } from "./WorkflowStudioHeader";

export function WorkflowStudioContent({
  workspaceId,
  conversationId,
  embedded = false,
  onBack,
  onError,
  onSuccess,
}: {
  workspaceId: string;
  conversationId: string;
  embedded?: boolean;
  onBack?: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
}) {
  const [nodeForm] = Form.useForm();
  const [fitViewSignal, setFitViewSignal] = useState(0);
  const navigate = useNavigate();
  const studio = useWorkflowStudio({
    workspaceId,
    conversationId,
    nodeForm,
    onError,
  });
  const backPath = conversationRoutePath(workspaceId, conversationId);

  const patchWorkflowSettings = (patch: Record<string, unknown>) => {
    if (!studio.workflow) return;
    const { output_mode: outputMode, ...settingsPatch } = patch;
    studio.setWorkflowDraft({
      ...studio.workflow,
      ...(typeof outputMode === "string" ? { output_mode: outputMode } : {}),
      settings: { ...workflowSettings(studio.workflow), ...settingsPatch },
    });
  };

  const saveWorkflow = async () => {
    if (!studio.workflow || studio.workflowGenerating) return;
    let parsed: ConversationWorkflow;
    try {
      parsed = layoutWorkflowPositions(
        JSON.parse(studio.workflowJson) as ConversationWorkflow,
      );
    } catch {
      onError("工作流 JSON 格式不正确");
      return;
    }
    const saved = await api.saveConversationWorkflow(conversationId, parsed);
    studio.setWorkflowDraft(saved);
    onSuccess("工作流已保存");
  };

  const generateWorkflow = async () => {
    if (!conversationId || studio.workflowGenerating) return;
    studio.setWorkflowGenerating(true);
    try {
      const generated = await api.generateConversationWorkflow(
        conversationId,
        studio.workflowInstruction,
      );
      studio.setWorkflowDraft({
        ...generated,
        settings: {
          ...workflowSettings(generated),
          generation_instruction: studio.workflowInstruction,
        },
      });
      onSuccess("AI 已生成工作流");
    } catch (error) {
      onError(error instanceof Error ? error.message : "AI 生成工作流失败");
    } finally {
      studio.setWorkflowGenerating(false);
    }
  };

  const runWorkflow = async () => {
    if (!studio.workflow) return;
    const run = await api.startWorkflowRun(conversationId, studio.workflow);
    studio.setWorkflowRuns((current) => [run, ...current]);
    onSuccess("工作流运行已创建");
  };

  if (studio.loading) {
    return (
      <main className={embedded ? "workflow-embedded-loading" : "workflow-studio-loading"}>
        <Spin />
      </main>
    );
  }

  const canvasPanel = (
    <WorkflowCanvasPanel
      workflow={studio.workflow}
      latestRun={studio.latestRun}
      workflowGenerating={studio.workflowGenerating}
      selectedNodeIds={studio.selectedNodeIds}
      selectedEdgeIds={studio.selectedEdgeIds}
      editingNodeState={studio.editingNodeState}
      workflowRuns={studio.workflowRuns}
      fitViewSignal={fitViewSignal}
      onCopySelection={studio.copySelection}
      onWorkflowChange={studio.setWorkflowDraft}
      onOpenNode={studio.openNodeEditor}
      onClearSelection={() => {
        studio.setSelectedNodeIds([]);
        studio.setSelectedEdgeIds([]);
        studio.setEditingNodeId(undefined);
      }}
      onSelectionChange={(nodeIds, edgeIds) => {
        studio.setSelectedNodeIds(nodeIds);
        studio.setSelectedEdgeIds(edgeIds);
        if (nodeIds.length === 1 && studio.workflow) {
          const node = studio.workflow.nodes.find(
            (item) => item.id === nodeIds[0],
          );
          if (node) studio.openNodeEditor(node);
        } else if (nodeIds.length > 1 || edgeIds.length) {
          studio.setEditingNodeId(undefined);
        }
      }}
    />
  );

  const nodeConfigPanel = (
    <WorkflowNodeConfigPanel
      nodeForm={nodeForm}
      editingNode={studio.editingNode}
      editingNodeState={studio.editingNodeState}
      latestRun={studio.latestRun}
      workflowEdges={studio.workflowEdges}
      workflowJson={studio.workflowJson}
      agentOptions={studio.agentOptions}
      toolOptions={studio.toolOptions}
      skillOptions={studio.skillOptions}
      mcpServerOptions={studio.mcpServerOptions}
      mcpToolOptions={studio.mcpToolOptions}
      onSaveNode={studio.saveWorkflowNode}
      onWorkflowJsonChange={studio.setWorkflowJson}
    />
  );

  if (embedded) {
    return (
      <section className="workflow-studio-embedded">
        <WorkflowModeToolbar
          workflow={studio.workflow}
          generating={studio.workflowGenerating}
          workflowInstruction={studio.workflowInstruction}
          newNodeType={studio.newNodeType}
          selectedNodeIds={studio.selectedNodeIds}
          selectedEdgeIds={studio.selectedEdgeIds}
          onBack={onBack ?? (() => navigate(backPath))}
          onSave={saveWorkflow}
          onGenerate={generateWorkflow}
          onRun={runWorkflow}
          onFitView={() => setFitViewSignal((value) => value + 1)}
          onInstructionChange={studio.setWorkflowInstruction}
          onNodeTypeChange={studio.setNewNodeType}
          onAddNode={studio.addWorkflowNode}
          onCopySelection={studio.copySelection}
          onDeleteSelection={studio.deleteSelection}
          onPatchSettings={patchWorkflowSettings}
        />
        {canvasPanel}
        {nodeConfigPanel}
      </section>
    );
  }

  return (
    <section className="workflow-studio-page">
      <WorkflowStudioHeader
        conversation={studio.conversation}
        workflow={studio.workflow}
        generating={studio.workflowGenerating}
        onBack={() => navigate(backPath)}
        onGenerate={generateWorkflow}
        onRun={runWorkflow}
        onSave={saveWorkflow}
        onPatchSettings={patchWorkflowSettings}
      />
      <div className="workflow-studio-main">
        <WorkflowNodePalette
          disabled={studio.workflowGenerating}
          onAdd={studio.addWorkflowNode}
        />
        {canvasPanel}
        {nodeConfigPanel}
      </div>
    </section>
  );
}
