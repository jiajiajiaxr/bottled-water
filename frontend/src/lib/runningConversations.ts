import type { AgentTask, ChatMessage, Conversation } from "../types";
import { isTaskRunning } from "./message";

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
  const knownConversationIds = new Set(conversations.map((item) => item.id));
  const running = new Set(
    [...localRunningConversationIds].filter((id) => knownConversationIds.has(id)),
  );

  backgroundTasks.forEach((task) => {
    if (
      task.conversation_id &&
      knownConversationIds.has(task.conversation_id) &&
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
