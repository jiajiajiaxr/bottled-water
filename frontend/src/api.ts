import {
  demoAgents,
  demoArtifact,
  demoConversations,
  demoDeployment,
  demoFiles,
  demoKnowledgeBases,
  demoMcpServers,
  demoModelConfigs,
  demoModelProviders,
  demoMessages,
  demoProjects,
  demoRemoteConnections,
  demoSandboxes,
  demoSkills,
  demoUser,
  demoWorkspaces
} from "./mock";
import type {
  Agent,
  AgentCapability,
  AgentConfigDraft,
  AgentTask,
  ChatMessage,
  Conversation,
  ConversationWorkflow,
  Deployment,
  AuditLog,
  KnowledgeBase,
  KnowledgeDocument,
  McpInvocation,
  McpServer,
  ModelConfig,
  ModelProvider,
  Project,
  RemoteConnection,
  SandboxCommandResult,
  SandboxSession,
  SecurityPermission,
  SecurityRole,
  SecurityUser,
  Skill,
  ToolDefinition,
  ToolInvokeResponse,
  UploadedFile,
  User,
  Workspace,
  WorkflowRun,
  WorkspaceArtifact
} from "./types";

const API_BASE = "/api/v1";

function unwrap<T>(payload: unknown): T {
  if (payload && typeof payload === "object" && "code" in payload && "data" in payload) {
    return (payload as { data: T }).data;
  }
  return payload as T;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = window.localStorage.getItem("agenthub_token");
  const isForm = init?.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {})
    }
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.clone().json();
      detail = payload?.message || payload?.detail || payload?.error || detail;
    } catch {
      try {
        detail = await response.clone().text();
      } catch {
        detail = response.statusText;
      }
    }
    throw new Error(`${response.status} ${detail}`);
  }

  return unwrap<T>(await response.json());
}

async function requestWithTimeout<T>(path: string, init: RequestInit, timeoutMs = 7000): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await request<T>(path, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

async function requestFile(path: string): Promise<{ previewUrl?: string; previewText?: string; contentType: string; filename?: string }> {
  const token = window.localStorage.getItem("agenthub_token");
  const response = await fetch(`${API_BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined
  });

  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }

  const contentType = response.headers.get("content-type") ?? "application/octet-stream";
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = /filename="?([^";]+)"?/i.exec(disposition)?.[1];

  if (contentType.startsWith("text/") || contentType.includes("json") || contentType.includes("xml")) {
    return { previewText: await response.text(), contentType, filename };
  }

  return { previewUrl: URL.createObjectURL(await response.blob()), contentType, filename };
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

function normalizeSkill(value: Skill & { status?: string; prompt?: string; content?: string; metadata?: Record<string, unknown> }): Skill {
  const rawTools = (value.tools ?? []) as unknown[];
  return {
    ...value,
    scope: value.scope ?? (value.workspace_id ? "workspace" : "platform"),
    enabled: value.enabled ?? value.status !== "disabled",
    prompt_template: value.prompt_template ?? value.prompt ?? value.content,
    tools: rawTools
      .map((tool) => (typeof tool === "string" ? tool : typeof tool === "object" && tool ? String((tool as { name?: unknown }).name ?? "") : ""))
      .filter(Boolean),
    mcp_server_id:
      value.mcp_server_id ??
      ((value.config?.mcp as { server_id?: string } | undefined)?.server_id)
  };
}

export const api = {
  async login(name: string, password = "agenthub"): Promise<User> {
    try {
      const result = await request<{ access_token: string; user: User }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username: name || "demo", email: name, password })
      });
      window.localStorage.setItem("agenthub_token", result.access_token);
      return result.user;
    } catch {
      return { ...demoUser, id: `user-${Date.now()}`, name: name || demoUser.name, role: "member" };
    }
  },

  async register(payload: { email: string; username: string; password: string; display_name?: string }): Promise<User> {
    const result = await request<{ access_token: string; user: User }>("/auth/signup", {
      method: "POST",
      body: JSON.stringify(payload)
    });
    window.localStorage.setItem("agenthub_token", result.access_token);
    return result.user;
  },

  async updateProfile(payload: { display_name?: string; name?: string; avatar_url?: string; settings?: Record<string, unknown> }): Promise<User> {
    return await request<User>("/auth/me", {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  },

  async changePassword(payload: { current_password: string; new_password: string }): Promise<{ changed: boolean }> {
    return await request<{ changed: boolean }>("/auth/password", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async demoLogin(): Promise<User> {
    try {
      const result = await request<{ access_token: string; user: User }>("/auth/demo", { method: "POST" });
      window.localStorage.setItem("agenthub_token", result.access_token);
      return result.user;
    } catch {
      await wait(250);
      return demoUser;
    }
  },

  async conversations(workspaceId?: string): Promise<Conversation[]> {
    try {
      const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
      const result = await request<{ items: Conversation[] } | Conversation[]>(`/conversations${query}`);
      return Array.isArray(result) ? result : result.items;
    } catch {
      return workspaceId ? demoConversations.filter((item) => !item.workspace_id || item.workspace_id === workspaceId) : demoConversations;
    }
  },

  async messages(conversationId: string): Promise<ChatMessage[]> {
    try {
      const result = await request<{ items: ChatMessage[] } | ChatMessage[]>(`/conversations/${conversationId}/messages`);
      return Array.isArray(result) ? result : result.items;
    } catch {
      return demoMessages[conversationId] ?? [];
    }
  },

  async createConversation(group = false): Promise<Conversation> {
    try {
      return await request<Conversation>("/conversations", {
        method: "POST",
        body: JSON.stringify({ chat_type: group ? "group" : "single" })
      });
    } catch {
      const now = new Date().toISOString();
      return {
        id: `conv-${Date.now()}`,
        chat_type: group ? "group" : "single",
        title: group ? "新的群聊" : "新的会话",
        participants: group
          ? [
              { id: "p-demo", participant_type: "agent", agent_name: "Master Agent", agent_type: "master", agent_status: "online", role: "owner" },
              { id: "p-agent", participant_type: "agent", agent_name: "Worker Agent", agent_type: "custom", agent_status: "online", role: "member" }
            ]
          : [{ id: "p-demo", participant_type: "agent", agent_name: "Master Agent", agent_type: "master", agent_status: "online", role: "owner" }],
        participant_count: group ? 2 : 1,
        agent_count: group ? 2 : 1,
        user_count: 1,
        updatedAt: now,
        pinned: false,
        archived: false,
        unread: 0,
        tags: group ? ["群聊"] : [],
        lastMessage: "开始新的协作。"
      };
    }
  },

  async createConversationWithAgents(payload: {
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
        body: JSON.stringify(payload)
      });
    } catch {
      const now = new Date().toISOString();
      const agents = demoAgents.filter((agent) => payload.participant_agent_ids.includes(agent.id));
      return {
        id: `conv-${Date.now()}`,
        chat_type: payload.chat_type,
        workspace_id: payload.workspace_id,
        title: payload.title || (payload.chat_type === "group" ? "新的多 Agent 群聊" : `${agents[0]?.name ?? "Agent"} 单聊`),
        participants: agents.map((agent, index) => ({
          id: `p-${agent.id}`,
          participant_type: "agent",
          agent_id: agent.id,
          agent_name: agent.name,
          agent_type: agent.type,
          agent_status: agent.status,
          role: index === 0 ? "owner" : "member"
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
        lastMessage: "会话已创建，可以发送任务开始协作。"
      };
    }
  },

  async updateConversation(id: string, patch: Partial<Conversation>): Promise<Conversation> {
    try {
      return await request<Conversation>(`/conversations/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          action:
            "pinned" in patch ? (patch.pinned ? "pin" : "unpin") : "archived" in patch ? (patch.archived ? "archive" : "unarchive") : "rename",
          title: patch.title,
          folder: patch.folder,
          category: patch.category,
          remark: patch.remark
        })
      });
    } catch {
      const current = demoConversations.find((item) => item.id === id);
      return { ...(current ?? demoConversations[0]), ...patch };
    }
  },

  async deleteConversation(id: string): Promise<{ id: string; deleted_at?: string }> {
    try {
      return await request<{ id: string; deleted_at?: string }>(`/conversations/${id}`, { method: "DELETE" });
    } catch {
      return { id, deleted_at: new Date().toISOString() };
    }
  },

  async sendMessage(conversationId: string, content: string, quotedMessageId?: string, attachments: UploadedFile[] = []): Promise<ChatMessage> {
    try {
      return await request<ChatMessage>(`/conversations/${conversationId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          client_message_id: `client-${Date.now()}`,
          content_type: "text",
          content: {
            text: content,
            attachments: attachments.map((file) => ({
              file_id: file.file_id ?? file.id,
              filename: file.original_filename,
              content_type: file.content_type,
              size: file.size
            }))
          },
          reply_to_message_id: quotedMessageId
        })
      });
    } catch {
      const normalizedAttachments = attachments.map((file) => ({
        file_id: file.file_id ?? file.id,
        filename: file.original_filename,
        original_filename: file.original_filename,
        content_type: file.content_type,
        size: file.size,
        parse_status: file.parse_status,
        public_url: file.public_url
      }));
      return {
        id: `msg-${Date.now()}`,
        conversationId,
        role: "user",
        kind: "text",
        author: demoUser.name,
        content,
        rawContent: { text: content, attachments: normalizedAttachments },
        attachments: normalizedAttachments,
        quotedMessageId,
        createdAt: new Date().toISOString()
      };
    }
  },

  async streamAssistantReply(
    conversationId: string,
    onDelta: (delta: string) => void,
    onDone?: () => void,
    onControl?: (stop: () => void) => void
  ): Promise<string> {
    try {
      const token = window.localStorage.getItem("agenthub_token");
      return await new Promise<string>((resolve, reject) => {
        let buffer = "";
        const source = new EventSource(
          `${API_BASE}/conversations/${conversationId}/stream?replay=false${token ? `&token=${encodeURIComponent(token)}` : ""}`
        );
        let timeout = 0;
        const stop = () => {
          window.clearTimeout(timeout);
          source.close();
          onDone?.();
          resolve(buffer);
        };
        onControl?.(stop);
        timeout = window.setTimeout(() => {
          source.close();
          onDone?.();
          resolve(buffer || "任务正在后台执行，稍后刷新可查看完整结果。");
        }, 120000);
        source.addEventListener("content_block_delta", (event) => {
          const payload = JSON.parse((event as MessageEvent).data);
          const delta = payload.delta?.text ?? "";
          buffer += delta;
          if (delta) onDelta(delta);
        });
        source.addEventListener("message_stop", () => {
          window.clearTimeout(timeout);
          source.close();
          onDone?.();
          resolve(buffer || "主控 Agent 已完成任务编排。");
        });
        source.addEventListener("error", () => {
          window.clearTimeout(timeout);
          source.close();
          if (buffer) {
            onDone?.();
            resolve(buffer);
          }
          else reject(new Error("stream failed"));
        });
      });
    } catch {
      await wait(350);
      const fallback = "模型流式连接暂不可用，任务已进入后台处理，可稍后刷新查看完整结果。";
      onDelta(fallback);
      onDone?.();
      return fallback;
    }
  },

  async assistantReply(conversationId: string, prompt: string): Promise<string> {
    let text = "";
    return await this.streamAssistantReply(conversationId, (delta) => {
      text += delta;
    }).then((result) => result || text || `收到：“${prompt}”。`);
  },

  async cancelAssistantReply(conversationId: string): Promise<{ cancelled: boolean }> {
    return await request<{ cancelled: boolean }>(`/conversations/${conversationId}/stream/cancel`, { method: "POST" });
  },

  async tasks(): Promise<AgentTask[]> {
    try {
      const result = await request<{ items: AgentTask[] } | AgentTask[]>("/tasks");
      return Array.isArray(result) ? result : result.items;
    } catch {
      return [];
    }
  },

  async createBackgroundTask(conversationId: string, prompt: string): Promise<AgentTask> {
    return await request<AgentTask>("/tasks", {
      method: "POST",
      body: JSON.stringify({ conversation_id: conversationId, prompt, title: prompt })
    });
  },

  async cancelTask(taskId: string): Promise<AgentTask> {
    return await request<AgentTask>(`/tasks/${taskId}/cancel`, { method: "POST" });
  },

  async artifact(conversationId: string): Promise<WorkspaceArtifact | undefined> {
    try {
      return await request<WorkspaceArtifact>(`/conversations/${conversationId}/artifact`);
    } catch {
      return undefined;
    }
  },

  async artifactById(artifactId: string): Promise<WorkspaceArtifact | undefined> {
    try {
      return await request<WorkspaceArtifact>(`/artifacts/${artifactId}`);
    } catch {
      return undefined;
    }
  },

  async conversationWorkflow(conversationId: string): Promise<ConversationWorkflow> {
    return await request<ConversationWorkflow>(`/conversations/${conversationId}/workflow`);
  },

  async saveConversationWorkflow(conversationId: string, workflow: ConversationWorkflow): Promise<ConversationWorkflow> {
    return await request<ConversationWorkflow>(`/conversations/${conversationId}/workflow`, {
      method: "PATCH",
      body: JSON.stringify(workflow)
    });
  },

  async generateConversationWorkflow(conversationId: string, instruction?: string): Promise<ConversationWorkflow> {
    return await request<ConversationWorkflow>(`/conversations/${conversationId}/workflow/generate`, {
      method: "POST",
      body: JSON.stringify({ instruction: instruction ?? "" })
    });
  },

  async workflowRuns(conversationId: string): Promise<WorkflowRun[]> {
    const result = await request<{ items: WorkflowRun[] }>(`/conversations/${conversationId}/workflow/runs`);
    return result.items;
  },

  async startWorkflowRun(conversationId: string, workflow?: ConversationWorkflow): Promise<WorkflowRun> {
    return await request<WorkflowRun>(`/conversations/${conversationId}/workflow/runs`, {
      method: "POST",
      body: JSON.stringify({ workflow })
    });
  },

  async updateWorkflowNode(conversationId: string, runId: string, nodeId: string, payload: { status: string; progress?: number; output?: Record<string, unknown>; message?: string }): Promise<WorkflowRun> {
    return await request<WorkflowRun>(`/conversations/${conversationId}/workflow/runs/${runId}/nodes/${encodeURIComponent(nodeId)}`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    });
  },

  async saveArtifact(artifact: WorkspaceArtifact): Promise<WorkspaceArtifact> {
    try {
      return await request<WorkspaceArtifact>(`/artifacts/${artifact.id}`, {
        method: "PUT",
        body: JSON.stringify({ files: { "index.html": artifact.code }, change_summary: "前端编辑保存" })
      });
    } catch {
      return { ...artifact, updatedAt: new Date().toISOString() };
    }
  },

  async exportArtifact(artifactId: string, format: string): Promise<{ previewUrl?: string; previewText?: string; contentType: string; filename?: string }> {
    return await requestFile(`/artifacts/${artifactId}/export?format=${encodeURIComponent(format)}`);
  },

  async deploy(conversationId: string, artifactId?: string): Promise<Deployment> {
    try {
      return await request<Deployment>("/deployments", {
        method: "POST",
        body: JSON.stringify({ conversationId, artifact_id: artifactId })
      });
    } catch {
      await wait(500);
      return { ...demoDeployment, updatedAt: new Date().toISOString() };
    }
  },

  async agents(params?: { search?: string; type?: string; status?: string }): Promise<Agent[]> {
    try {
      const query = new URLSearchParams();
      Object.entries(params ?? {}).forEach(([key, value]) => value && query.set(key, value));
      const result = await request<{ items: Agent[] } | Agent[]>(`/agents${query.toString() ? `?${query}` : ""}`);
      return Array.isArray(result) ? result : result.items;
    } catch {
      return demoAgents;
    }
  },

  async createAgent(payload: AgentConfigDraft): Promise<Agent> {
    try {
      return await request<Agent>("/agents", {
        method: "POST",
        body: JSON.stringify({
          ...payload,
          type: "custom",
          provider: "custom",
          config: { ...(payload.config ?? {}), model_config_id: payload.model_config_id }
        })
      });
    } catch {
      return {
        id: `agent-${Date.now()}`,
        name: payload.name,
        display_name: payload.name,
        type: "custom",
        version: "1.0",
        avatar_color: "#6b7280",
        capabilities: payload.capabilities,
        description: payload.description,
        status: "online",
        provider: "custom",
        is_official: false,
        response_latency_ms: 1100,
        config: { ...payload.config, tools: payload.tools, system_prompt: payload.system_prompt, base_agent_id: payload.base_agent_id, model_config_id: payload.model_config_id }
      };
    }
  },

  async updateAgent(agentId: string, payload: Partial<AgentConfigDraft> & { display_name?: string; status?: Agent["status"] }): Promise<Agent> {
    try {
      return await request<Agent>(`/agents/${agentId}`, {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
    } catch {
      const current = demoAgents.find((agent) => agent.id === agentId) ?? demoAgents[0];
      return {
        ...current,
        name: payload.name ?? current.name,
        display_name: payload.display_name ?? payload.name ?? current.display_name,
        description: payload.description ?? current.description,
        capabilities: payload.capabilities ?? current.capabilities,
        status: payload.status ?? current.status,
        config: {
          ...(current.config ?? {}),
          ...(payload.config ?? {}),
          ...(payload.system_prompt ? { system_prompt: payload.system_prompt } : {}),
          ...(payload.tools ? { tools: payload.tools } : {})
        }
      };
    }
  },

  async deleteAgent(agentId: string): Promise<{ id: string; deleted: boolean }> {
    try {
      return await request<{ id: string; deleted: boolean }>(`/agents/${agentId}`, { method: "DELETE" });
    } catch {
      return { id: agentId, deleted: true };
    }
  },

  async parseCapabilities(text: string): Promise<{ items: AgentCapability[]; system_prompt: string }> {
    try {
      return await request<{ items: AgentCapability[]; system_prompt: string }>("/agents/parse-capabilities", {
        method: "POST",
        body: JSON.stringify({ text })
      });
    } catch {
      return {
        items: [
          { label: "任务分析", category: "通用", proficiency: 4 },
          { label: "结构化输出", category: "通用", proficiency: 4 }
        ],
        system_prompt: `你是${text}。请输出结构清晰、可执行、可验证的结果。`
      };
    }
  },

  async generateAgentConfig(text: string, base_agent_id?: string, preferred_tools: string[] = []): Promise<AgentConfigDraft> {
    try {
      return await requestWithTimeout<AgentConfigDraft>("/agents/generate", {
        method: "POST",
        body: JSON.stringify({ text, brief: text, base_agent_id, preferred_tools })
      }, 10000);
    } catch {
        const dictionary: Array<[string, string, string]> = [
          ["React", "编码", "file.read"],
          ["前端", "编码", "file.write"],
          ["后端", "架构", "sandbox.run"],
          ["API", "架构", "api.test"],
          ["测试", "测试", "test.run"],
          ["知识库", "RAG", "file.summarize"],
          ["检索", "RAG", "file.summarize"],
          ["部署", "运维", "deploy.preview"],
          ["审查", "质量", "document.review"]
        ];
        const matched = dictionary.filter(([label]) => text.toLowerCase().includes(label.toLowerCase()));
        const fallbackCapabilities: Array<[string, string, string]> = [
          ["任务分析", "通用", "file.summarize"],
          ["结构化输出", "通用", "file.extract_text"]
        ];
        const capabilities = (matched.length ? matched : fallbackCapabilities).map(([label, category]) => ({
          label,
          category,
          proficiency: 4
        }));
        const tools = Array.from(new Set(matched.map(([, , tool]) => tool).filter(Boolean)));
        const baseName = text.replace(/\s+/g, "").replace(/[，。,.]/g, "").slice(0, 14);
        return {
          name: baseName ? `${baseName} Agent` : "自定义 Agent",
          description: text.slice(0, 180) || "由 AI 生成配置的自定义 Agent。",
          capabilities,
          system_prompt: `你是${text || "一个自定义 Agent"}。请保持结构化、可验证、可执行，并在需要时调用已授权工具。`,
          tools: tools.length ? tools : ["file.extract_text"],
          config: { temperature: 0.7, generated_by: "frontend_fallback" },
          capability_text: text,
          temperature: 0.7
        };
    }
  },

  async generateAgent(text: string, base_agent_id?: string, preferred_tools: string[] = []): Promise<AgentConfigDraft> {
    return this.generateAgentConfig(text, base_agent_id, preferred_tools);
  },

  async testAgent(agentId: string, message: string): Promise<{ response: string }> {
    return await request<{ response: string }>(`/agents/${agentId}/test`, {
      method: "POST",
      body: JSON.stringify({ message })
    });
  },

  async addParticipants(conversationId: string, agentIds: string[]): Promise<Conversation> {
    try {
      return await request<Conversation>(`/conversations/${conversationId}/participants`, {
        method: "POST",
        body: JSON.stringify({ agent_ids: agentIds, role: "member" })
      });
    } catch {
      const current = demoConversations[0];
      return current;
    }
  },

  async removeParticipant(conversationId: string, participantId: string): Promise<Conversation> {
    return await request<Conversation>(`/conversations/${conversationId}/participants/${participantId}`, {
      method: "DELETE"
    });
  },

  async uploadFile(file: File, conversationId?: string, purpose = "attachment"): Promise<UploadedFile> {
    try {
      const form = new FormData();
      form.append("file", file);
      if (conversationId) form.append("conversation_id", conversationId);
      form.append("purpose", purpose);
      return await request<UploadedFile>("/files/upload", { method: "POST", body: form });
    } catch {
      return {
        id: `file-${Date.now()}`,
        filename: file.name,
        original_filename: file.name,
        content_type: file.type || "application/octet-stream",
        size: file.size,
        purpose,
        parse_status: "stored",
        created_at: new Date().toISOString()
      };
    }
  },

  async files(conversationId?: string): Promise<UploadedFile[]> {
    try {
      const query = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : "";
      const result = await request<{ items: UploadedFile[] }>(`/files${query}`);
      return result.items;
    } catch {
      return demoFiles;
    }
  },

  async previewFile(fileId: string): Promise<{ previewUrl?: string; previewText?: string; contentType: string; filename?: string }> {
    return await requestFile(`/files/${fileId}/download`);
  },

  async knowledgeBases(): Promise<KnowledgeBase[]> {
    try {
      const result = await request<{ items: KnowledgeBase[] }>("/knowledge-bases");
      return result.items;
    } catch {
      return demoKnowledgeBases;
    }
  },

  async createKnowledgeBase(payload: { name: string; description: string; scope: string; visibility: string }): Promise<KnowledgeBase> {
    try {
      return await request<KnowledgeBase>("/knowledge-bases", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return { id: `kb-${Date.now()}`, document_count: 0, chunk_count: 0, total_tokens: 0, status: "ready", ...payload };
    }
  },

  async importKnowledgeText(kbId: string, payload: { title: string; content: string }): Promise<KnowledgeDocument> {
    return await request<KnowledgeDocument>(`/knowledge-bases/${kbId}/documents`, {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async retrieveKnowledge(kbId: string, query: string): Promise<{ items: Array<{ title: string; score: number; text: string }>; context: string }> {
    try {
      return await request<{ items: Array<{ title: string; score: number; text: string }>; context: string }>(
        `/knowledge-bases/${kbId}/retrieve`,
        { method: "POST", body: JSON.stringify({ query, top_k: 5, mode: "hybrid" }) }
      );
    } catch {
      return { items: [], context: "暂无检索结果" };
    }
  },

  async workspaces(): Promise<Workspace[]> {
    try {
      const result = await request<{ items: Workspace[] }>("/workspaces");
      return result.items;
    } catch {
      return demoWorkspaces;
    }
  },

  async createWorkspace(payload: { name: string; description: string; type: string; tags: string[]; config?: Record<string, unknown> }): Promise<Workspace> {
    try {
      return await request<Workspace>("/workspaces", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return {
        id: `workspace-${Date.now()}`,
        status: "active",
        member_count: 1,
        project_count: 0,
        ...payload
      };
    }
  },

  async projects(workspaceId: string): Promise<Project[]> {
    try {
      const result = await request<{ items: Project[] }>(`/workspaces/${workspaceId}/projects`);
      return result.items;
    } catch {
      return demoProjects.filter((project) => project.workspace_id === workspaceId);
    }
  },

  async createProject(workspaceId: string, payload: { name: string; description: string; type: string }): Promise<Project> {
    try {
      return await request<Project>(`/workspaces/${workspaceId}/projects`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return {
        id: `project-${Date.now()}`,
        workspace_id: workspaceId,
        status: "active",
        tags: [],
        file_count: 0,
        current_version: 1,
        ...payload
      };
    }
  },

  async saveProjectFile(projectId: string, payload: { path: string; language: string; content: string }): Promise<{ path: string; version: number }> {
    return await request<{ path: string; version: number }>(`/projects/${projectId}/files`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  async modelProviders(): Promise<ModelProvider[]> {
    try {
      const result = await request<{ items: ModelProvider[] }>("/model-providers");
      return result.items;
    } catch {
      return demoModelProviders;
    }
  },

  async createModelProvider(payload: {
    name: string;
    provider_type: string;
    base_url: string;
    api_key?: string;
    default_model: string;
    supports_streaming?: boolean;
    supports_embeddings?: boolean;
    config?: Record<string, unknown>;
  }): Promise<ModelProvider> {
    try {
      return await request<ModelProvider>("/model-providers", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return {
        id: `provider-${Date.now()}`,
        name: payload.name,
        provider_type: payload.provider_type,
        base_url: payload.base_url,
        default_model: payload.default_model,
        supports_streaming: payload.supports_streaming ?? true,
        supports_embeddings: payload.supports_embeddings ?? false,
        config: payload.config,
        status: "active"
      };
    }
  },

  async modelConfigs(): Promise<ModelConfig[]> {
    try {
      const result = await request<{ items: ModelConfig[] }>("/model-configs");
      return result.items;
    } catch {
      return demoModelConfigs;
    }
  },

  async createModelConfig(payload: {
    provider_id: string;
    name: string;
    model_id: string;
    purpose: string;
    context_window?: number;
    max_output_tokens?: number;
    temperature_default?: number;
    config?: Record<string, unknown>;
  }): Promise<ModelConfig> {
    try {
      return await request<ModelConfig>("/model-configs", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return {
        id: `model-${Date.now()}`,
        provider_id: payload.provider_id,
        name: payload.name,
        model_id: payload.model_id,
        purpose: payload.purpose,
        context_window: payload.context_window ?? 128000,
        max_output_tokens: payload.max_output_tokens ?? 4096,
        temperature_default: payload.temperature_default ?? 0.4,
        config: payload.config,
        status: "active"
      };
    }
  },

  async testModel(prompt: string, model_config_id?: string): Promise<{ response: string; model: string; usage?: Record<string, unknown> }> {
    return await request<{ response: string; model: string; usage?: Record<string, unknown> }>("/model-configs/test", {
      method: "POST",
      body: JSON.stringify({ prompt, model_config_id })
    });
  },

  async mcpServers(workspaceId?: string): Promise<McpServer[]> {
    try {
      const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
      const result = await request<{ items: McpServer[] }>(`/mcp-servers${query}`);
      return result.items;
    } catch {
      return workspaceId ? demoMcpServers.filter((item) => item.workspace_id === workspaceId) : demoMcpServers;
    }
  },

  async createMcpServer(payload: {
    workspace_id?: string;
    name: string;
    transport: string;
    url?: string;
    command?: string;
    args?: string[];
    env?: Record<string, string>;
    headers?: Record<string, string>;
    enabled?: boolean;
    tool_filter?: string[];
    timeout_ms?: number;
    retry?: number;
  }): Promise<McpServer> {
    try {
      return await request<McpServer>("/mcp-servers", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return {
        id: `mcp-${Date.now()}`,
        workspace_id: payload.workspace_id,
        name: payload.name,
        transport: payload.transport as McpServer["transport"],
        url: payload.url,
        command: payload.command,
        args: payload.args ?? [],
        env: payload.env,
        headers: payload.headers,
        enabled: payload.enabled ?? true,
        health_status: "unknown",
        tools: [],
        tool_filter: payload.tool_filter ?? [],
        timeout_ms: payload.timeout_ms ?? 30000,
        retry: payload.retry ?? 1
      };
    }
  },

  async importMcpServer(payload: { workspace_id?: string; source_type: "manifest_url" | "json" | string; source: string }): Promise<McpServer> {
    try {
      return await request<McpServer>("/mcp-servers/import", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      let parsed: Partial<McpServer> & { name?: string } = {};
      if (payload.source_type === "json") {
        try {
          const value = JSON.parse(payload.source);
          parsed = Array.isArray(value?.mcpServers) ? value.mcpServers[0] ?? {} : value;
        } catch {
          parsed = {};
        }
      }
      const sourceLooksRemote = /^https?:\/\//i.test(payload.source.trim());
      return {
        id: `mcp-import-${Date.now()}`,
        workspace_id: payload.workspace_id,
        name: parsed.name ?? (sourceLooksRemote ? "导入的远程 MCP" : "导入的 MCP 服务"),
        transport: (parsed.transport as McpServer["transport"]) ?? (sourceLooksRemote ? "httpStream" : "stdio"),
        url: parsed.url ?? (sourceLooksRemote ? payload.source.trim() : undefined),
        command: parsed.command ?? (sourceLooksRemote ? undefined : payload.source.trim().split(/\s+/)[0]),
        args: parsed.args ?? [],
        enabled: parsed.enabled ?? true,
        health_status: "unknown",
        tools: parsed.tools ?? [],
        tool_filter: parsed.tool_filter ?? [],
        timeout_ms: parsed.timeout_ms ?? 30000,
        retry: parsed.retry ?? 1
      };
    }
  },

  async probeMcpServer(id: string): Promise<McpServer> {
    try {
      return await request<McpServer>(`/mcp-servers/${id}/probe`, { method: "POST" });
    } catch {
      const current = demoMcpServers.find((item) => item.id === id) ?? demoMcpServers[0];
      return { ...current, health_status: "online", last_checked_at: new Date().toISOString() };
    }
  },

  async invokeMcpTool(serverId: string, toolName: string, argumentsValue: Record<string, unknown> = {}, conversationId?: string): Promise<McpInvocation> {
    return await request<McpInvocation>(`/mcp-servers/${serverId}/tools/${encodeURIComponent(toolName)}/invoke`, {
      method: "POST",
      body: JSON.stringify({ arguments: argumentsValue, conversation_id: conversationId })
    });
  },

  async deleteMcpServer(serverId: string): Promise<{ id: string; deleted: boolean }> {
    return await request<{ id: string; deleted: boolean }>(`/mcp-servers/${serverId}`, { method: "DELETE" });
  },

  async mcpInvocations(serverId?: string): Promise<McpInvocation[]> {
    const query = serverId ? `?server_id=${encodeURIComponent(serverId)}` : "";
    const result = await request<{ items: McpInvocation[] }>(`/mcp-invocations${query}`);
    return result.items;
  },

  async skills(workspaceId?: string): Promise<Skill[]> {
    try {
      const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
      const result = await request<{ items: Skill[] } | Skill[]>(`/skills${query}`);
      return (Array.isArray(result) ? result : result.items).map((skill) => normalizeSkill(skill));
    } catch {
      return workspaceId ? demoSkills.filter((skill) => !skill.workspace_id || skill.workspace_id === workspaceId) : demoSkills;
    }
  },

  async createSkill(payload: {
    workspace_id?: string;
    name: string;
    description: string;
    category: string;
    scope: string;
    prompt_template?: string;
    tools: string[];
    enabled?: boolean;
    config?: Record<string, unknown>;
  }): Promise<Skill> {
    try {
      const result = await request<Skill>("/skills", {
        method: "POST",
        body: JSON.stringify({
          workspace_id: payload.workspace_id,
          name: payload.name,
          description: payload.description,
          category: payload.category,
          source: "manual",
          status: payload.enabled === false ? "disabled" : "active",
          content: payload.prompt_template ?? "",
          prompt: payload.prompt_template ?? "",
          tools: payload.tools.map((name) => ({ name, enabled: true })),
          tags: [payload.scope],
          config: payload.config ?? {}
        })
      });
      return normalizeSkill(result);
    } catch {
      return {
        id: `skill-${Date.now()}`,
        workspace_id: payload.workspace_id,
        name: payload.name,
        description: payload.description,
        category: payload.category,
        scope: payload.scope,
        version: "1.0.0",
        enabled: payload.enabled ?? true,
        source: "manual",
        prompt_template: payload.prompt_template,
        tools: payload.tools,
        config: payload.config,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
    }
  },

  async importMcpAsSkill(payload: { workspace_id?: string; mcp_server_id: string; name?: string; category?: string }): Promise<Skill> {
    try {
      return normalizeSkill(await request<Skill>("/skills/import-mcp", {
        method: "POST",
        body: JSON.stringify(payload)
      }));
    } catch {
      const server = demoMcpServers.find((item) => item.id === payload.mcp_server_id);
      return {
        id: `skill-mcp-${Date.now()}`,
        workspace_id: payload.workspace_id ?? server?.workspace_id,
        name: payload.name || `${server?.name ?? "MCP"} Skill`,
        description: `由 ${server?.name ?? payload.mcp_server_id} 导入的 MCP 工具能力。`,
        category: payload.category ?? "mcp",
        scope: "workspace",
        version: "1.0.0",
        enabled: true,
        source: "mcp",
        mcp_server_id: payload.mcp_server_id,
        tools: server?.tools?.map((tool) => tool.name) ?? server?.tool_filter ?? [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
    }
  },

  async generateSkill(payload: {
    workspace_id?: string;
    name?: string;
    intent: string;
    requirements?: string;
    category?: string;
    tags?: string[];
  }): Promise<Skill> {
    return normalizeSkill(await request<Skill>("/skills/generate", {
      method: "POST",
      body: JSON.stringify(payload)
    }));
  },

  async testSkill(skillId: string, input: string): Promise<{ status: string; response: string; model: string; usage?: Record<string, unknown> }> {
    return await request<{ status: string; response: string; model: string; usage?: Record<string, unknown> }>(`/skills/${skillId}/test`, {
      method: "POST",
      body: JSON.stringify({ input, message: input })
    });
  },

  async deleteSkill(skillId: string): Promise<{ id: string; deleted: boolean }> {
    return await request<{ id: string; deleted: boolean }>(`/skills/${skillId}`, { method: "DELETE" });
  },

  async tools(workspaceId?: string): Promise<ToolDefinition[]> {
    try {
      const query = workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : "";
      const result = await request<{ items: ToolDefinition[] }>(`/tools${query}`);
      return result.items;
    } catch {
      return [
        {
          id: "file.extract_text",
          name: "file.extract_text",
          display_name: "提取文本",
          description: "从上传文件提取可供模型读取的文本。",
          category: "file",
          type: "builtin",
          status: "active",
          version: "1.0.0",
          permissions: ["file:read"],
          tags: ["file"],
          is_builtin: true
        },
        {
          id: "artifact.create_pdf",
          name: "artifact.create_pdf",
          display_name: "生成 PDF",
          description: "创建 PDF 产物并返回产物卡片。",
          category: "artifact",
          type: "builtin",
          status: "active",
          version: "1.0.0",
          permissions: ["artifact:create"],
          tags: ["artifact"],
          is_builtin: true
        }
      ];
    }
  },

  async createTool(payload: {
    workspace_id?: string;
    name: string;
    display_name?: string;
    description: string;
    category: string;
    type?: string;
    permissions?: string[];
    implementation?: Record<string, unknown>;
    runtime?: Record<string, unknown>;
    tags?: string[];
  }): Promise<ToolDefinition> {
    return await request<ToolDefinition>("/tools", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async generateTool(payload: {
    workspace_id?: string;
    name?: string;
    intent: string;
    requirements?: string;
    category?: string;
    allowed_permissions?: string[];
    tags?: string[];
  }): Promise<ToolDefinition> {
    return await request<ToolDefinition>("/tools/generate", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  async invokeTool(toolId: string, argumentsValue: Record<string, unknown> = {}, workspaceId?: string): Promise<ToolInvokeResponse> {
    return await request<ToolInvokeResponse>(`/tools/${encodeURIComponent(toolId)}/invoke`, {
      method: "POST",
      body: JSON.stringify({ arguments: argumentsValue, workspace_id: workspaceId })
    });
  },

  async deleteTool(toolId: string): Promise<{ id: string; deleted: boolean }> {
    return await request<{ id: string; deleted: boolean }>(`/tools/${encodeURIComponent(toolId)}`, { method: "DELETE" });
  },

  async sandboxes(): Promise<SandboxSession[]> {
    try {
      const result = await request<{ items: SandboxSession[] }>("/sandboxes");
      return result.items;
    } catch {
      return demoSandboxes;
    }
  },

  async createSandbox(payload: {
    workspace_id?: string;
    project_id?: string;
    name: string;
    image: string;
    resource_limits?: Record<string, unknown>;
  }): Promise<SandboxSession> {
    try {
      return await request<SandboxSession>("/sandboxes", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return {
        id: `sandbox-${Date.now()}`,
        workspace_id: payload.workspace_id,
        project_id: payload.project_id,
        name: payload.name,
        image: payload.image,
        resource_limits: payload.resource_limits,
        status: "ready",
        command_history: []
      };
    }
  },

  async runSandboxCommand(
    sandboxId: string,
    payload: { command: string; timeout_seconds?: number; cwd?: string; env?: Record<string, string> }
  ): Promise<{ sandbox: SandboxSession; result: SandboxCommandResult }> {
    try {
      return await request<{ sandbox: SandboxSession; result: SandboxCommandResult }>(`/sandboxes/${sandboxId}/commands`, {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      const result: SandboxCommandResult = {
        command: payload.command,
        argv: payload.command.split(" "),
        exit_code: 0,
        stdout: `[mock-sandbox] ${payload.command}`,
        stderr: "",
        duration_ms: 300,
        created_at: new Date().toISOString()
      };
      const sandbox = demoSandboxes.find((item) => item.id === sandboxId) ?? demoSandboxes[0];
      return { sandbox: { ...sandbox, command_history: [result, ...sandbox.command_history] }, result };
    }
  },

  async remoteConnections(): Promise<RemoteConnection[]> {
    try {
      const result = await request<{ items: RemoteConnection[] }>("/remote-connections");
      return result.items;
    } catch {
      return demoRemoteConnections;
    }
  },

  async createRemoteConnection(payload: {
    workspace_id?: string;
    name: string;
    connection_type: string;
    endpoint: string;
    capabilities?: string[];
  }): Promise<RemoteConnection> {
    try {
      return await request<RemoteConnection>("/remote-connections", {
        method: "POST",
        body: JSON.stringify(payload)
      });
    } catch {
      return {
        id: `remote-${Date.now()}`,
        workspace_id: payload.workspace_id,
        name: payload.name,
        connection_type: payload.connection_type,
        endpoint: payload.endpoint,
        capabilities: payload.capabilities ?? [],
        status: "disconnected"
      };
    }
  },

  async connectRemote(id: string): Promise<RemoteConnection> {
    try {
      return await request<RemoteConnection>(`/remote-connections/${id}/connect`, { method: "POST" });
    } catch {
      const current = demoRemoteConnections.find((item) => item.id === id) ?? demoRemoteConnections[0];
      return { ...current, status: "connected", last_connected_at: new Date().toISOString() };
    }
  },

  async auditLogs(): Promise<AuditLog[]> {
    const result = await request<{ items: AuditLog[] }>("/audit-logs?page_size=100");
    return result.items;
  },

  async auditStats(): Promise<{ total: number; high_risk: number; by_action: Record<string, number>; latest_at?: string }> {
    return await request<{ total: number; high_risk: number; by_action: Record<string, number>; latest_at?: string }>("/audit-logs/stats");
  },

  async securityRoles(): Promise<SecurityRole[]> {
    const result = await request<{ items: SecurityRole[] }>("/security/roles");
    return result.items;
  },

  async securityPermissions(): Promise<SecurityPermission[]> {
    const result = await request<{ items: SecurityPermission[] }>("/security/permissions");
    return result.items;
  },

  async securityUsers(): Promise<SecurityUser[]> {
    const result = await request<{ items: SecurityUser[] }>("/security/users");
    return result.items;
  }
};
