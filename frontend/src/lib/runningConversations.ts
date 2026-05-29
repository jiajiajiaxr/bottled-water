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
  return runtimeStatus === "cancelled" || conversation.lastMessage === "已停止本次响应";
}

function hasTerminalRuntime(conversation: Conversation, hasLocalRunning: boolean) {
  if (hasLocalRunning) return false;
  const status = String(conversation.workflow_runtime?.status || "").toLowerCase();
  return TERMINAL_RUNTIME_STATUSES.has(status);
}
