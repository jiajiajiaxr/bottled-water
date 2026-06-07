import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  CloudUploadOutlined,
  BulbOutlined,
  FileSearchOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  App as AntApp,
  Avatar,
  Button,
  Empty,
  Flex,
  Layout,
  Mentions,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import type { UploadProps } from "antd";
import { api } from "@/api";
import { MessageBubble } from "@/features/chat/components/MessageBubble";
import { RuntimeDecisionStrip } from "@/features/chat/components/ChatPanel/RuntimeDecisionStrip";
import {
  displayNodeName,
  displayNodePath,
  formatSize,
  sourceLabel,
  walk,
} from "@/features/workspaceFiles/workspaceFileUtils";
import { useMessageStore, useConversationStore } from "@/store";
import { useMessageOperations } from "@/hooks";
import type {
  ChatMessage,
  Conversation,
  ModelConfig,
  UploadedFile,
  WorkspaceFileNode,
} from "@/types";
import type { MessageAgentMention, MessageFileReference } from "@/types/messages";

const { Content } = Layout;
const { Text } = Typography;
const AGENT_MODEL_SENTINEL = "__agent_model__";
const UPLOAD_ACCEPT =
  ".txt,.md,.markdown,.json,.csv,.tsv,.html,.htm,.xml,.pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.gif,.webp,.bmp,.svg,.py,.js,.jsx,.ts,.tsx,.css,.scss,.zip";
const ALLOWED_UPLOAD_EXTENSIONS = new Set(UPLOAD_ACCEPT.split(","));
const BLOCKED_UPLOAD_EXTENSIONS = new Set([
  ".exe",
  ".dll",
  ".bat",
  ".cmd",
  ".ps1",
  ".msi",
  ".com",
  ".scr",
  ".vbs",
  ".lnk",
  ".reg",
]);

type WorkspaceFileOption = {
  value: string;
  label: ReactNode;
  searchText: string;
  node: WorkspaceFileNode;
};

type AgentMentionOption = {
  value: string;
  label: ReactNode;
  searchText: string;
  agent: MessageAgentMention;
};

export function ChatPanel({
  active,
  loading,
  userName,
  userAvatarUrl,
  defaultModelConfigId,
  onPreviewArtifact,
}: {
  active?: Conversation;
  loading: boolean;
  userName?: string;
  userAvatarUrl?: string;
  defaultModelConfigId?: string;
  onPreviewArtifact?: (message: ChatMessage) => void;
}) {
  const [text, setText] = useState("");
  const [quoted, setQuoted] = useState<ChatMessage>();
  const [pendingFiles, setPendingFiles] = useState<UploadedFile[]>([]);
  const [contextReferences, setContextReferences] = useState<
    MessageFileReference[]
  >([]);
  const [agentMentions, setAgentMentions] = useState<MessageAgentMention[]>([]);
  const [workspaceFileOptions, setWorkspaceFileOptions] = useState<
    WorkspaceFileOption[]
  >([]);
  const [workspaceFilesLoading, setWorkspaceFilesLoading] = useState(false);
  const [awaitingResponse, setAwaitingResponse] = useState(false);
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const { message } = AntApp.useApp();
  const { send, cancel, streamingMessages, displayOrder } = useMessageOperations(
    userName,
    userAvatarUrl,
  );
  const localRunningConversationIds = useConversationStore(
    (s) => s.localRunningConversationIds,
  );
  const [stopping, setStopping] = useState(false);

  // 从 Conversation Store 读取当前会话的思考模式状态（持久化）
  const thinkingEnabled = useConversationStore((s) =>
    active ? s.getThinkingEnabled(active.id) : false,
  );
  const setThinkingEnabled = useCallback(
    (enabled: boolean) => {
      if (active) {
        useConversationStore.getState().setThinkingEnabled(active.id, enabled);
      }
    },
    [active],
  );
  const selectedModelConfigId = useConversationStore((s) =>
    active ? s.getSelectedModelConfigId(active.id) : undefined,
  );
  const setSelectedModelConfigId = useCallback(
    (value: string) => {
      if (active) {
        useConversationStore.getState().setSelectedModelConfigId(active.id, value);
      }
    },
    [active],
  );

  useEffect(() => {
    if (!active?.id) return;
    const snippet = useConversationStore.getState().consumeDraftSnippet(active.id);
    if (!snippet) return;
    setText((current) => `${current}${current && !current.endsWith(" ") ? " " : ""}${snippet}`);
  }, [active?.id]);

  useEffect(() => {
    setContextReferences([]);
    setAgentMentions([]);
  }, [active?.id]);

  useEffect(() => {
    if (!active?.workspace_id) {
      setWorkspaceFileOptions([]);
      return;
    }
    let alive = true;
    setWorkspaceFilesLoading(true);
    api
      .workspaceFileTree(active.workspace_id)
      .then((tree) => {
        if (!alive) return;
        setWorkspaceFileOptions(workspaceFileOptionsFromTree(tree.root));
      })
      .catch(() => {
        if (alive) setWorkspaceFileOptions([]);
      })
      .finally(() => {
        if (alive) setWorkspaceFilesLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [active?.workspace_id]);

  // 历史消息从 Store 读取
  const historyMessages = useMessageStore((s) => s.historyMessages);
  const historyConversationId = useMessageStore((s) => s.historyConversationId);
  const messageVersions = useMessageStore((s) => s.messageVersions);
  const activeHistoryMessages = useMemo(() => {
    if (!active?.id || historyConversationId !== active.id) return [];
    return historyMessages.filter((item) => item.conversationId === active.id);
  }, [active?.id, historyConversationId, historyMessages]);

  // 合并所有消息用于 quoted 查找
  const allMessages = useMemo(
    () => [...activeHistoryMessages, ...streamingMessages.values()],
    [activeHistoryMessages, streamingMessages],
  );
  const chatDefaultModelConfigId =
    defaultModelConfigId ||
    modelConfigs.find((item) => item.status === "active")?.id ||
    modelConfigs[0]?.id;
  const chatModelSelectValue =
    selectedModelConfigId || chatDefaultModelConfigId || AGENT_MODEL_SENTINEL;
  const runtimeModelConfigId =
    chatModelSelectValue === AGENT_MODEL_SENTINEL ? undefined : chatModelSelectValue;
  const modelOptions = useMemo(
    () => [
      ...modelConfigs.map((item) => ({
        label: `${item.name || item.model_id} · ${item.provider_name || item.model_id}`,
        value: item.id,
      })),
      {
        label: "跟随 Agent 绑定模型",
        value: AGENT_MODEL_SENTINEL,
      },
    ],
    [modelConfigs],
  );
  const agentMentionOptions = useMemo(
    () => agentMentionOptionsFromParticipants(active?.participants ?? []),
    [active?.participants],
  );

  const submit = async () => {
    let value =
      text.trim() || (pendingFiles.length ? "请结合上传附件继续处理。" : "");
    if (!text.trim() && pendingFiles.length) {
      value = "请结合上传附件继续处理。";
    }
    if (!value || !active) return;
    const filesToSend = pendingFiles;
    const refsToSend = contextReferences;
    const mentionsToSend = agentMentions;
    const quotedMessage = quoted;
    setAwaitingResponse(true);
    setText("");
    setQuoted(undefined);
    setPendingFiles([]);
    setContextReferences([]);
    setAgentMentions([]);
    try {
      await send(
        value,
        quotedMessage,
        filesToSend,
        thinkingEnabled,
        runtimeModelConfigId,
        refsToSend,
        mentionsToSend,
      );
    } catch (error) {
      setText(value);
      setQuoted(quotedMessage);
      setPendingFiles(filesToSend);
      setContextReferences(refsToSend);
      setAgentMentions(mentionsToSend);
      throw error;
    }
  };

  const isWorking = Boolean(
    active &&
      (awaitingResponse ||
        streamingMessages.size > 0 ||
        localRunningConversationIds.has(active.id) ||
        active.generation_status === "running" ||
        active.generation_status === "executing"),
  );
  const hasVisibleStreamingMessage = streamingMessages.size > 0 || displayOrder.length > 0;
  const showThinkingIndicator = Boolean(
    active && isWorking && !hasVisibleStreamingMessage,
  );

  const stopResponse = async () => {
    if (!active || stopping) return;
    setStopping(true);
    try {
      await cancel(active.id);
      setAwaitingResponse(false);
    } finally {
      setStopping(false);
    }
  };

  const copy = useCallback(
    async (value: string) => {
      await navigator.clipboard.writeText(value);
      message.success("已复制");
    },
    [message],
  );

  // 用 Map 缓存 quoted 查找，避免每条消息渲染时都做 O(n) 遍历
  const messageById = useMemo(() => {
    const map = new Map<string, ChatMessage>();
    for (const item of allMessages) {
      map.set(item.id, item);
    }
    return map;
  }, [allMessages]);

  const handleQuote = useCallback((msg: ChatMessage) => setQuoted(msg), []);
  const handleCopy = useCallback((value: string) => copy(value), [copy]);
  const messageListRef = useRef<HTMLDivElement>(null);
  const isAtBottom = useRef(true);

  const handleComposerTextChange = useCallback((value: string) => {
    setText(value);
    setAgentMentions((current) =>
      current.filter((mention) =>
        mention.agent_name ? mentionTokenPresent(value, mention.agent_name) : true,
      ),
    );
  }, []);

  const addAgentMention = useCallback(
    (mention: MessageAgentMention) => {
      setAgentMentions((current) => {
        if (current.some((item) => item.agent_id === mention.agent_id)) {
          return current;
        }
        return [...current, mention];
      });
    },
    [],
  );

  const removeAgentMention = useCallback(
    (agentId: string) => {
      const mention = agentMentions.find((item) => item.agent_id === agentId);
      setAgentMentions((current) =>
        current.filter((item) => item.agent_id !== agentId),
      );
      if (mention?.agent_name) {
        setText((current) => removeMentionToken(current, mention.agent_name || ""));
      }
    },
    [agentMentions],
  );

  const addContextReference = useCallback(
    (value: string) => {
      const option = workspaceFileOptions.find((item) => item.value === value);
      if (!option) return;
      const reference = fileReferenceFromNode(option.node);
      setContextReferences((current) => {
        if (current.some((item) => fileReferenceKey(item) === fileReferenceKey(reference))) {
          message.info("该文件已在上下文引用中");
          return current;
        }
        return [...current, reference];
      });
    },
    [message, workspaceFileOptions],
  );

  const removeContextReference = useCallback((key: string) => {
    setContextReferences((current) =>
      current.filter((item) => fileReferenceKey(item) !== key),
    );
  }, []);

  const uploadProps: UploadProps = {
    multiple: true,
    accept: UPLOAD_ACCEPT,
    showUploadList: false,
    beforeUpload: async (file) => {
      if (!active?.id) {
        message.warning("请先选择一个会话");
        return Upload.LIST_IGNORE;
      }
      const suffix = file.name.includes(".")
        ? `.${file.name.split(".").pop()!.toLowerCase()}`
        : "";
      if (
        BLOCKED_UPLOAD_EXTENSIONS.has(suffix) ||
        (suffix && !ALLOWED_UPLOAD_EXTENSIONS.has(suffix))
      ) {
        message.warning("暂不支持上传该文件类型");
        return Upload.LIST_IGNORE;
      }
      try {
        const uploaded = await api.uploadFile(
          file,
          active.id,
          "attachment",
          active.workspace_id,
        );
        setPendingFiles((current) => {
          if (current.some((item) => item.id === uploaded.id)) return current;
          return [...current, uploaded];
        });
        message.success(`${uploaded.original_filename || file.name} 已加入输入框`);
      } catch (error) {
        message.error(error instanceof Error ? error.message : "文件上传失败");
      }
      return Upload.LIST_IGNORE;
    },
  };

  useEffect(() => {
    setPendingFiles([]);
  }, [active?.id]);

  useEffect(() => {
    const el = messageListRef.current;
    if (!el) return;

    const handleScroll = () => {
      const threshold = 50;
      isAtBottom.current =
        el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    };

    el.addEventListener("scroll", handleScroll, { passive: true });
    return () => el.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    if (!isAtBottom.current) return;
    const el = messageListRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [activeHistoryMessages, displayOrder]);

  // 进入新对话且消息加载完成后，滚动到底部
  useEffect(() => {
    if (!active?.id || loading) return;
    isAtBottom.current = true;
    const el = messageListRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [active?.id, loading]);

  useEffect(() => {
    let alive = true;
    api.modelConfigs()
      .then((items) => {
        if (alive) {
          setModelConfigs(items);
        }
      })
      .catch(() => {
        if (alive) {
          setModelConfigs([]);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  // 智能体开始回复后，隐藏思考中指示器
  useEffect(() => {
    if (awaitingResponse && (streamingMessages.size > 0 || displayOrder.length > 0)) {
      setAwaitingResponse(false);
    }
  }, [streamingMessages.size, displayOrder.length, awaitingResponse]);

  useEffect(() => {
    if (!active || active.generation_status === "idle") {
      setAwaitingResponse(false);
    }
  }, [active?.id, active?.generation_status]);

  const renderMessageBubble = (item: ChatMessage) => {
    return (
      <MessageBubble
        key={item.id}
        message={item}
        workspaceId={active?.workspace_id}
        currentUserAvatarUrl={userAvatarUrl}
        version={messageVersions.get(item.id) ?? 0}
        quoted={
          item.quotedMessageId
            ? messageById.get(item.quotedMessageId)
            : undefined
        }
        onQuote={handleQuote}
        onCopy={handleCopy}
        onPreview={(message) => onPreviewArtifact?.(message)}
      />
    );
  };

  return (
    <Content className="chat-panel">
      <RuntimeDecisionStrip conversation={active} />
      <div ref={messageListRef} className="message-list">
        {loading ? (
          <Spin />
        ) : allMessages.length ? (
          <>
            {activeHistoryMessages.map(renderMessageBubble)}
            {displayOrder.map((agentId) => {
              const msg = streamingMessages.get(agentId);

              return msg ? renderMessageBubble(msg) : null;
            })}
            {showThinkingIndicator && (
              <div className="thinking-indicator">
                <div className="thinking-indicator-dots">
                  <span className="dot" />
                  <span className="dot" />
                  <span className="dot" />
                </div>
                <span className="thinking-indicator-text">思考中</span>
              </div>
            )}
          </>
        ) : (
          <Empty description="暂无消息" />
        )}
      </div>
      <div className="composer">
        {quoted && (
          <div className="composer-quote">
            <div className="composer-quote-text">
              <Text type="secondary">引用：{quoted.content}</Text>
            </div>
            <Button
              type="text"
              size="small"
              onClick={() => setQuoted(undefined)}
            >
              取消
            </Button>
          </div>
        )}
        {pendingFiles.length > 0 && (
          <div className="composer-files" data-testid="composer-attachments">
            {pendingFiles.map((file) => (
              <Tag
                key={file.id}
                closable
                icon={<CloudUploadOutlined />}
                onClose={() =>
                  setPendingFiles((current) =>
                    current.filter((item) => item.id !== file.id),
                  )
                }
              >
                {file.original_filename} · {Math.ceil(file.size / 1024)}KB ·{" "}
                {file.parse_status}
              </Tag>
            ))}
          </div>
        )}
        <Mentions
          data-testid="message-input"
          aria-label="message-input"
          className="composer-mentions"
          autoSize={{ minRows: 2, maxRows: 6 }}
          value={text}
          prefix="@"
          options={agentMentionOptions}
          placeholder="输入消息，键入 @ 可选择群聊 Agent；Enter 发送，Shift+Enter 换行"
          onChange={handleComposerTextChange}
          onSelect={(option) => {
            const selected = agentMentionOptions.find(
              (item) => item.value === String(option.value || ""),
            );
            if (selected) addAgentMention(selected.agent);
          }}
          filterOption={(input, option) => {
            const searchText = String(
              (option as AgentMentionOption | undefined)?.searchText ||
                option?.value ||
                "",
            ).toLowerCase();
            return searchText.includes(input.toLowerCase());
          }}
          notFoundContent="暂无可 @ 的 Agent"
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        {(contextReferences.length > 0 || agentMentions.length > 0) && (
          <div className="composer-contexts" data-testid="composer-contexts">
            <Text type="secondary" className="composer-contexts-label">
              引用/指定
            </Text>
            {agentMentions.map((mention) => (
              <Tag
                key={mention.agent_id}
                closable
                icon={<RobotOutlined />}
                onClose={() => removeAgentMention(mention.agent_id)}
              >
                {mention.agent_name ?? mention.agent_id}
              </Tag>
            ))}
            {contextReferences.map((reference) => (
              <Tag
                key={fileReferenceKey(reference)}
                closable
                icon={<FileSearchOutlined />}
                onClose={() => removeContextReference(fileReferenceKey(reference))}
              >
                {reference.filename ?? reference.path}
              </Tag>
            ))}
          </div>
        )}
        <Flex justify="space-between" align="center">
          <Space>
            <Upload {...uploadProps}>
              <Button icon={<CloudUploadOutlined />} data-testid="file-upload">
                上传文件
              </Button>
            </Upload>
            <Select
              className="composer-context-select"
              showSearch
              allowClear
              value={undefined}
              placeholder="引用工作区文件"
              loading={workspaceFilesLoading}
              disabled={!active?.workspace_id}
              options={workspaceFileOptions}
              optionFilterProp="searchText"
              onSelect={(value) => {
                if (typeof value === "string") addContextReference(value);
              }}
              popupMatchSelectWidth={420}
              data-testid="context-reference-select"
              suffixIcon={<FileSearchOutlined />}
              notFoundContent={
                workspaceFilesLoading ? "加载中..." : "暂无可引用文件"
              }
            />
            <Select
              className="composer-model-select"
              size="middle"
              value={chatModelSelectValue}
              options={modelOptions}
              onChange={setSelectedModelConfigId}
              disabled={!active || modelOptions.length === 0}
              popupMatchSelectWidth={280}
              data-testid="composer-model-select"
            />
          </Space>
          <Space>
            <Tooltip title={thinkingEnabled ? "已开启思考模式" : "思考模式"}>
              <Button
                type="default"
                className={thinkingEnabled ? "thinking-toggle-button active" : "thinking-toggle-button"}
                icon={<BulbOutlined />}
                onClick={() => setThinkingEnabled(!thinkingEnabled)}
                disabled={!active}
                data-testid="thinking-toggle"
              >
                思考
              </Button>
            </Tooltip>
            {isWorking && (
              <Button
                type="default"
                danger
                icon={<StopOutlined />}
                loading={stopping}
                onClick={stopResponse}
                disabled={!active}
                data-testid="stop-response"
              >
                停止
              </Button>
            )}
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={submit}
              disabled={!active}
              data-testid="send-message"
            >
              发送
            </Button>
          </Space>
        </Flex>
      </div>
    </Content>
  );
}

function workspaceFileOptionsFromTree(root: WorkspaceFileNode): WorkspaceFileOption[] {
  const nodes: WorkspaceFileNode[] = [];
  walk([root], (node) => {
    if (node.type === "file") nodes.push(node);
  });
  return nodes.map((node) => {
    const name = displayNodeName(node);
    const path = displayNodePath(node);
    return {
      value: node.id || node.path,
      searchText: `${name} ${node.path} ${node.display_path ?? ""}`,
      node,
      label: (
        <div className="composer-context-option">
          <span className="composer-context-option-name">{name}</span>
          <span className="composer-context-option-meta">
            {path} · {sourceLabel(node.source)} · {formatSize(node.size ?? 0)}
          </span>
        </div>
      ),
    };
  });
}

function fileReferenceFromNode(node: WorkspaceFileNode): MessageFileReference {
  const fileId = node.id.startsWith("file:") ? node.id.slice(5) : undefined;
  return {
    path: node.path,
    file_id: fileId,
    node_id: node.id,
    filename: displayNodeName(node),
    content_type: node.mime_type,
    size: node.size,
    source: node.source,
    display_path: node.display_path ?? displayNodePath(node),
  };
}

function fileReferenceKey(reference: MessageFileReference) {
  return reference.file_id
    ? `file:${reference.file_id}`
    : `path:${reference.path}`;
}

function agentMentionOptionsFromParticipants(
  participants: Conversation["participants"],
): AgentMentionOption[] {
  return participants
    .filter((participant) => (
      participant.participant_type === "agent" &&
      !participant.left_at &&
      Boolean(participant.agent_id)
    ))
    .map((participant) => {
      const agentId = String(participant.agent_id);
      const name = participant.agent_name || participant.nickname || agentId;
      const mention: MessageAgentMention = {
        agent_id: agentId,
        agent_name: name,
        agent_avatar_url: participant.agent_avatar_url,
      };
      return {
        value: name,
        searchText: `${name} ${agentId} ${participant.agent_type ?? ""}`,
        agent: mention,
        label: (
          <div className="composer-agent-mention-option">
            <Avatar
              size={28}
              src={participant.agent_avatar_url}
              className="composer-agent-mention-avatar"
            >
              {name.slice(0, 1).toUpperCase()}
            </Avatar>
            <div className="composer-agent-mention-text">
              <span className="composer-agent-mention-name">{name}</span>
              <span className="composer-agent-mention-meta">
                {participant.agent_type || "Agent"}
              </span>
            </div>
          </div>
        ),
      };
    });
}

function mentionTokenPresent(text: string, name: string) {
  return text.toLowerCase().includes(`@${name}`.toLowerCase());
}

function removeMentionToken(text: string, name: string) {
  const escaped = escapeRegExp(name);
  return text
    .replace(new RegExp(`@${escaped}\\s*`, "gi"), "")
    .replace(/[ \t]{2,}/g, " ")
    .trimStart();
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
