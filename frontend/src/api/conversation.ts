import { request } from "./client";
import { demoConversations, demoAgents } from "@/mock";
import type { Conversation } from "@/types";

export async function conversations(workspaceId?: string): Promise<Conversation[]> {
  try {
    const query = workspaceId
      ? `?workspace_id=${encodeURIComponent(workspaceId)}`
      : "";
    const result = await request<{ items: Conversation[] } | Conversation[]>(
      `/conversations${query}`,
    );
    return Array.isArray(result) ? result : result.items;
  } catch {
    return workspaceId
      ? demoConversations.filter(
          (item) => !item.workspace_id || item.workspace_id === workspaceId,
        )
      : demoConversations;
  }
}

export async function createConversation(group = false): Promise<Conversation> {
  try {
    return await request<Conversation>("/conversations", {
      method: "POST",
      body: JSON.stringify({ chat_type: group ? "group" : "single" }),
    });
  } catch {
    const now = new Date().toISOString();
    return {
      id: `conv-${Date.now()}`,
      chat_type: group ? "group" : "single",
      title: group ? "新的群聊" : "新的会话",
      participants: group
        ? [
            {
              id: "p-demo",
              participant_type: "agent",
              agent_name: "Master Agent",
              agent_type: "master",
              agent_status: "online",
              role: "owner",
            },
            {
              id: "p-agent",
              participant_type: "agent",
              agent_name: "Worker Agent",
              agent_type: "custom",
              agent_status: "online",
              role: "member",
            },
          ]
        : [
            {
              id: "p-demo",
              participant_type: "agent",
              agent_name: "Master Agent",
              agent_type: "master",
              agent_status: "online",
              role: "owner",
            },
          ],
      participant_count: group ? 2 : 1,
      agent_count: group ? 2 : 1,
      user_count: 1,
      updatedAt: now,
      pinned: false,
      archived: false,
      unread: 0,
      tags: group ? ["群聊"] : [],
      lastMessage: "开始新的协作。",
    };
  }
}

export async function createConversationWithAgents(payload: {
  chat_type: "single" | "group";
  title?: string;
  participant_agent_ids: string[];
  master_enabled?: boolean;
  workspace_id?: string;
  folder?: string;
  category?: string;
}): Promise<Conversation> {
  try {
    return await request<Conversation>("/conversations", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch {
    const now = new Date().toISOString();
    const agents = demoAgents.filter((agent) =>
      payload.participant_agent_ids.includes(agent.id),
    );
    return {
      id: `conv-${Date.now()}`,
      chat_type: payload.chat_type,
      workspace_id: payload.workspace_id,
      title:
        payload.title ||
        (payload.chat_type === "group"
          ? "新的多 Agent 群聊"
          : `${agents[0]?.name ?? "Agent"} 单聊`),
      participants: agents.map((agent, index) => ({
        id: `p-${agent.id}`,
        participant_type: "agent",
        agent_id: agent.id,
        agent_name: agent.name,
        agent_type: agent.type,
        agent_status: agent.status,
        role: index === 0 ? "owner" : "member",
      })),
      participant_count: agents.length,
      agent_count: agents.length,
      user_count: 1,
      updatedAt: now,
      pinned: false,
      archived: false,
      unread: 0,
      tags: payload.chat_type === "group" ? ["群聊"] : ["单聊"],
      folder: payload.folder || payload.category || "Default",
      category: payload.category || payload.folder || "Default",
      lastMessage: "会话已创建，可以发送任务开始协作。",
    };
  }
}

export async function updateConversation(
  id: string,
  patch: Partial<Conversation>,
): Promise<Conversation> {
  try {
    return await request<Conversation>(`/conversations/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        action:
          "pinned" in patch
            ? patch.pinned
              ? "pin"
              : "unpin"
            : "archived" in patch
              ? patch.archived
                ? "archive"
                : "unarchive"
              : "rename",
        title: patch.title,
        folder: patch.folder,
        category: patch.category,
        remark: patch.remark,
      }),
    });
  } catch {
    const current = demoConversations.find((item) => item.id === id);
    return { ...(current ?? demoConversations[0]), ...patch };
  }
}

export async function deleteConversation(
  id: string,
): Promise<{ id: string; deleted_at?: string }> {
  try {
    return await request<{ id: string; deleted_at?: string }>(
      `/conversations/${id}`,
      { method: "DELETE" },
    );
  } catch {
    return { id, deleted_at: new Date().toISOString() };
  }
}

export async function addParticipants(
  conversationId: string,
  agentIds: string[],
): Promise<Conversation> {
  try {
    return await request<Conversation>(
      `/conversations/${conversationId}/participants`,
      {
        method: "POST",
        body: JSON.stringify({ agent_ids: agentIds, role: "member" }),
      },
    );
  } catch {
    const current = demoConversations[0];
    return current;
  }
}

export async function removeParticipant(
  conversationId: string,
  participantId: string,
): Promise<Conversation> {
  return await request<Conversation>(
    `/conversations/${conversationId}/participants/${participantId}`,
    {
      method: "DELETE",
    },
  );
}
