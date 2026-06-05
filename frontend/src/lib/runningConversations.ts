import type { AgentTask, ChatMessage, Conversation } from "../types";
import { isTaskRunning } from "./message";

const TERMINAL_RUNTIME_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "canceled",
]);

export function deriveRunningConversationIds({
  conversations,
  backgroundTasks,
  localRunningConversationIds,
  activeConversationId,
  activeMessages,
}: {
  conversations: Conversation[];
  backgroundTasks: AgentTask[];
  localRunningConversationIds: Set<string>;
  activeConversationId?: string;
  activeMessages: ChatMessage[];
}) {
  const conversationById = new Map(conversations.map((item) => [item.id, item]));
  const running = new Set(
    [...localRunningConversationIds].filter((id) => {
      const conversation = conversationById.get(id);
      return Boolean(conversation) && !hasCancelledSignal(conversation);
    }),
  );

  conversations.forEach((conversation) => {
    if (hasBackendRunningSignal(conversation) && !hasTerminalRuntime(conversation, running.has(conversation.id))) {
      running.add(conversation.id);
    }
  });

  backgroundTasks.forEach((task) => {
    const conversation = task.conversation_id
      ? conversationById.get(task.conversation_id)
      : undefined;
    if (
      task.conversation_id &&
      conversation &&
      !hasTerminalRuntime(conversation, running.has(task.conversation_id)) &&
      isTaskRunning(task.status)
    ) {
      running.add(task.conversation_id);
    }
  });

  if (
    activeConversationId &&
    activeMessages.some(
      (message) =>
        message.conversationId === activeConversationId &&
        (message.streamState === "streaming" || message.status === "streaming"),
    )
  ) {
    running.add(activeConversationId);
  }

  return running;
}

function hasCancelledSignal(conversation?: Conversation) {
  if (!conversation) return false;
  const runtimeStatus = String(conversation.workflow_runtime?.status || "").toLowerCase();
  const generationStatus = String(conversation.generation_status || "").toLowerCase();
  const latestGenerationStatus = String(latestGeneration(conversation)?.status || "").toLowerCase();
  return (
    runtimeStatus === "cancelled" ||
    generationStatus === "cancelled" ||
    latestGenerationStatus === "cancelled" ||
    conversation.lastMessage === "已停止本次响应"
  );
}

function hasTerminalRuntime(conversation: Conversation, hasLocalRunning: boolean) {
  if (hasLocalRunning) return false;
  const workflowStatus = String(conversation.workflow_runtime?.status || "").toLowerCase();
  const generationStatus = String(conversation.generation_status || "").toLowerCase();
  const latestGenerationStatus = String(latestGeneration(conversation)?.status || "").toLowerCase();
  return (
    TERMINAL_RUNTIME_STATUSES.has(workflowStatus) ||
    generationStatus === "idle" ||
    TERMINAL_RUNTIME_STATUSES.has(generationStatus) ||
    TERMINAL_RUNTIME_STATUSES.has(latestGenerationStatus)
  );
}

function hasBackendRunningSignal(conversation: Conversation) {
  if (String(conversation.generation_status || "").toLowerCase() === "running") {
    return true;
  }
  const runtime = conversation.runtime;
  if (!runtime?.active_generation_id) return false;
  const active = (runtime.generations || []).find((item) => item.id === runtime.active_generation_id);
  return !active || !TERMINAL_RUNTIME_STATUSES.has(String(active.status || "").toLowerCase());
}

function latestGeneration(conversation: Conversation) {
  const generations = conversation.runtime?.generations || [];
  return generations.length ? generations[generations.length - 1] : undefined;
}
