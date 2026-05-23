import {
  App as AntApp,
  Avatar,
  Badge,
  Button,
  Card,
  Checkbox,
  Divider,
  Drawer,
  Empty,
  Flex,
  Form,
  Input,
  Layout,
  List,
  Modal,
  Popover,
  Progress,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import type { UploadRequestOption } from "rc-upload/lib/interface";
import {
  ApiOutlined,
  AppstoreOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  CopyOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DiffOutlined,
  EditOutlined,
  EyeOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  LoginOutlined,
  MessageOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
  ReloadOutlined,
  RobotOutlined,
  RocketOutlined,
  SearchOutlined,
  SendOutlined,
  TeamOutlined,
  ToolOutlined,
  UserAddOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api } from "./api";
import type {
  Agent,
  AgentCapability,
  AgentTask,
  AuditLog,
  ChatMessage,
  Conversation,
  Deployment,
  KnowledgeBase,
  MessageAttachment,
  McpInvocation,
  McpServer,
  ModelConfig,
  ModelProvider,
  Project,
  RemoteConnection,
  SandboxCommandResult,
  SandboxSession,
  SecurityRole,
  SecurityUser,
  Skill,
  ToolDefinition,
  ConversationWorkflow,
  WorkflowNode,
  UploadedFile,
  User,
  Workspace,
  WorkflowRun,
  WorkspaceArtifact,
} from "./types";
import {
  CONVERSATION_CATEGORY_OPTIONS,
  LEGACY_DEFAULT_CONVERSATION_CATEGORIES,
  normalizeConversationCategory,
  mergeConversationCategories,
} from "./lib/conversation";
import { formatTime, formatFileSize } from "./lib/format";
import {
  makeMessage,
  messageAttachments,
  attachmentName,
  stripInternalAgentOutput,
  isTaskRunning,
  isLikelyArtifactRequest,
  participantName,
} from "./lib/message";
import { renderInlineMarkdown, MarkdownContent } from "./lib/markdown";
import { buildPreviewDocument } from "./lib/preview";
import { diffLines } from "./lib/diff";
import {
  WORKFLOW_NODE_TYPE_OPTIONS,
  WORKFLOW_NODE_TYPE_LABEL,
  workflowNodeType,
  createWorkflowNode,
} from "./lib/workflow";

const { Header, Sider, Content } = Layout;
const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;


function LoginScreen({ onLogin }: { onLogin: (user: User) => void }) {
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const { message } = AntApp.useApp();

  const submit = async (values: {
    email?: string;
    username?: string;
    display_name?: string;
    password?: string;
  }) => {
    setLoading(true);
    try {
      if (mode === "register") {
        onLogin(
          await api.register({
            email: values.email ?? "",
            username: values.username || values.email?.split("@")[0] || "",
            display_name:
              values.display_name || values.username || values.email,
            password: values.password ?? "",
          }),
        );
        message.success("注册成功，已登录");
      } else {
        onLogin(
          await api.login(
            values.email ?? "demo",
            values.password ?? "agenthub",
          ),
        );
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  const demo = async () => {
    setLoading(true);
    try {
      onLogin(await api.demoLogin());
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-panel">
        <div>
          <Text type="secondary">AgentHub</Text>
          <Title level={1}>IM 多 Agent 工作台</Title>
          <Paragraph>
            登录后进入会话、Agent、文件、知识库和部署一体化协作空间。
          </Paragraph>
        </div>
        <Segmented
          block
          className="login-mode"
          value={mode}
          onChange={(value) => setMode(value as "login" | "register")}
          options={[
            { label: "登录", value: "login" },
            { label: "注册", value: "register" },
          ]}
        />
        <Form key={mode} layout="vertical" onFinish={submit}>
          <Form.Item
            label="Email"
            name="email"
            initialValue={mode === "login" ? "demo" : undefined}
            rules={
              mode === "register"
                ? [{ required: true, type: "email", message: "请输入有效邮箱" }]
                : undefined
            }
          >
            <Input
              size="large"
              prefix={<LoginOutlined />}
              placeholder="demo 或邮箱"
              aria-label="email"
            />
          </Form.Item>
          {mode === "register" && (
            <>
              <Form.Item
                label="用户名"
                name="username"
                rules={[{ required: true, message: "请输入用户名" }]}
              >
                <Input size="large" placeholder="agenthub-user" />
              </Form.Item>
              <Form.Item label="显示名称" name="display_name">
                <Input size="large" placeholder="你的名字" />
              </Form.Item>
            </>
          )}
          <Form.Item
            label="Password"
            name="password"
            initialValue={mode === "login" ? "agenthub" : undefined}
            rules={
              mode === "register"
                ? [{ required: true, min: 6, message: "密码至少 6 位" }]
                : undefined
            }
          >
            <Input.Password
              size="large"
              placeholder="agenthub"
              aria-label="password"
            />
          </Form.Item>
          <Space className="login-actions">
            <Button
              type="primary"
              htmlType="submit"
              size="large"
              loading={loading}
            >
              {mode === "register" ? "注册并登录" : "登录"}
            </Button>
            <Button
              size="large"
              icon={<ApiOutlined />}
              onClick={demo}
              loading={loading}
              data-testid="demo-login"
              disabled={mode === "register"}
            >
              演示用户
            </Button>
          </Space>
        </Form>
      </section>
    </main>
  );
}

function ConversationSidebar({
  conversations,
  activeId,
  runningConversationIds,
  categoryOptions,
  onSelect,
  onCreate,
  onCreateCategory,
  onTogglePin,
  onToggleArchive,
  onDelete,
  onEdit,
}: {
  conversations: Conversation[];
  activeId?: string;
  runningConversationIds: Set<string>;
  categoryOptions: string[];
  onSelect: (id: string) => void;
  onCreate: (group: boolean) => void;
  onCreateCategory: (name: string) => void;
  onTogglePin: (item: Conversation) => void;
  onToggleArchive: (item: Conversation) => void;
  onDelete: (item: Conversation) => void;
  onEdit: (item: Conversation, patch: Partial<Conversation>) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"active" | "archived">("active");
  const [folder, setFolder] = useState("all");
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [editing, setEditing] = useState<Conversation>();
  const [editForm] = Form.useForm();

  const folders = useMemo(() => {
    const names = conversations.map(
      (item) => item.folder || item.category || "Default",
    );
    return ["all", ...mergeConversationCategories(categoryOptions, names)];
  }, [categoryOptions, conversations]);

  const selectCategoryOptions = useMemo(() => {
    const existing = conversations.map(
      (item) => item.folder || item.category || "Default",
    );
    return mergeConversationCategories(categoryOptions, existing).map(
      (name) => ({ label: name, value: name }),
    );
  }, [categoryOptions, conversations]);

  const visible = useMemo(() => {
    return conversations
      .filter((item) =>
        filter === "archived" ? item.archived : !item.archived,
      )
      .filter(
        (item) =>
          folder === "all" ||
          (item.folder || item.category || "Default") === folder,
      )
      .filter((item) =>
        `${item.title} ${item.lastMessage} ${item.tags.join(" ")}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      )
      .sort(
        (a, b) =>
          Number(b.pinned) - Number(a.pinned) ||
          +new Date(b.updatedAt) - +new Date(a.updatedAt),
      );
  }, [conversations, filter, folder, query]);

  const submitNewFolder = () => {
    const name = newFolderName.trim();
    if (!name) return;
    onCreateCategory(name);
    setFolder(name);
    setNewFolderName("");
    setCreatingFolder(false);
  };

  return (
    <Sider width={320} className="sidebar">
      <div className="sidebar-head">
        <div>
          <Text type="secondary">Workspace</Text>
          <Title level={3}>会话</Title>
        </div>
        <Space>
          <Tooltip title="新建单聊">
            <Button
              shape="circle"
              type="primary"
              icon={<UserAddOutlined />}
              onClick={() => onCreate(false)}
              data-testid="new-chat"
            />
          </Tooltip>
          <Tooltip title="新建群聊">
            <Button
              shape="circle"
              icon={<TeamOutlined />}
              onClick={() => onCreate(true)}
              data-testid="new-group-chat"
            />
          </Tooltip>
        </Space>
      </div>
      <Input
        className="search-box"
        prefix={<SearchOutlined />}
        placeholder="搜索会话、标签或消息"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <Segmented
        block
        value={filter}
        onChange={(value) => setFilter(value as "active" | "archived")}
        options={[
          { label: "进行中", value: "active" },
          { label: "归档", value: "archived" },
        ]}
      />
      <div className="conversation-folders">
        <div className="folder-section-head">
          <Text type="secondary">文件夹</Text>
          <Tooltip title="新建分类">
            <Button
              size="small"
              shape="circle"
              icon={<FolderAddOutlined />}
              onClick={() => setCreatingFolder((value) => !value)}
            />
          </Tooltip>
        </div>
        {creatingFolder && (
          <Input.Search
            className="folder-create-input"
            size="small"
            autoFocus
            placeholder="新建分类名称"
            value={newFolderName}
            enterButton="添加"
            onChange={(event) => setNewFolderName(event.target.value)}
            onSearch={submitNewFolder}
          />
        )}
        {folders.map((name) => (
          <button
            key={name}
            className={`folder-item ${folder === name ? "is-active" : ""}`}
            onClick={() => setFolder(name)}
          >
            {name === "all" ? <InboxOutlined /> : <FolderOpenOutlined />}
            <span>{name === "all" ? "All" : name}</span>
          </button>
        ))}
      </div>
      <List
        className="conversation-list"
        dataSource={visible}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无会话"
            />
          ),
        }}
        renderItem={(item) => {
          const running = runningConversationIds.has(item.id);
          return (
            <div
              role="button"
              tabIndex={0}
              className={`conversation-item ${item.id === activeId ? "is-active" : ""} ${running ? "is-running" : ""}`}
              onClick={() => onSelect(item.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ")
                  onSelect(item.id);
              }}
            >
              <div className="conversation-main">
                <Flex justify="space-between" align="center">
                  <Text strong ellipsis>
                    {item.title}
                  </Text>
                  <Text type="secondary" className="time">
                    {formatTime(item.updatedAt)}
                  </Text>
                </Flex>
                <Text type="secondary" ellipsis className="last-message">
                  {item.lastMessage || (running ? "正在回答..." : "")}
                </Text>
                <Space size={[4, 4]} wrap>
                  {running && <Tag color="processing">正在回答</Tag>}
                  <Tag
                    icon={
                      item.chat_type === "group" ? (
                        <TeamOutlined />
                      ) : (
                        <MessageOutlined />
                      )
                    }
                  >
                    {item.chat_type === "group"
                      ? `${item.agent_count ?? item.participants.length} Agent`
                      : "单聊"}
                  </Tag>
                  {item.tags.map((tag) => (
                    <Tag key={tag}>{tag}</Tag>
                  ))}
                  {(item.folder || item.category) && (
                    <Tag color="purple">{item.folder || item.category}</Tag>
                  )}
                  {item.unread > 0 && (
                    <Badge count={item.unread} size="small" />
                  )}
                </Space>
              </div>
              <Space direction="vertical" size={6}>
                <Tooltip title={item.pinned ? "取消置顶" : "置顶"}>
                  <Button
                    size="small"
                    shape="circle"
                    icon={item.pinned ? <PushpinFilled /> : <PushpinOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      onTogglePin(item);
                    }}
                  />
                </Tooltip>
                <Tooltip title={item.archived ? "移出归档" : "归档"}>
                  <Button
                    size="small"
                    shape="circle"
                    icon={<InboxOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggleArchive(item);
                    }}
                  />
                </Tooltip>
                <Tooltip title="Edit">
                  <Button
                    size="small"
                    shape="circle"
                    icon={<EditOutlined />}
                    onClick={(event) => {
                      event.stopPropagation();
                      setEditing(item);
                      editForm.setFieldsValue({
                        title: item.title,
                        folder: item.folder || item.category || "Default",
                        remark: item.remark || "",
                      });
                    }}
                  />
                </Tooltip>
                {item.archived && (
                  <Tooltip title="删除归档">
                    <Button
                      size="small"
                      danger
                      shape="circle"
                      icon={<DeleteOutlined />}
                      onClick={(event) => {
                        event.stopPropagation();
                        onDelete(item);
                      }}
                    />
                  </Tooltip>
                )}
              </Space>
            </div>
          );
        }}
      />
      <Modal
        title="Edit conversation"
        open={Boolean(editing)}
        onCancel={() => setEditing(undefined)}
        onOk={() => editForm.submit()}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={(values) => {
            if (!editing) return;
            onEdit(editing, values);
            setEditing(undefined);
          }}
        >
          <Form.Item name="title" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="folder" label="Folder / category">
            <Select options={selectCategoryOptions} placeholder="选择分类" />
          </Form.Item>
          <Form.Item name="remark" label="Remark">
            <TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Sider>
  );
}

function MessageBubble({
  message,
  quoted,
  onQuote,
  onRegenerate,
  onCopy,
  onPreview,
}: {
  message: ChatMessage;
  quoted?: ChatMessage;
  onQuote: (message: ChatMessage) => void;
  onRegenerate: (message: ChatMessage) => void;
  onCopy: (text: string) => void;
  onPreview: (message: ChatMessage) => void;
}) {
  const isUser = message.role === "user";
  const isEvent =
    message.kind === "event" ||
    message.role === "system" ||
    message.role === "tool";
  const attachments = messageAttachments(message);
  const [previewAttachment, setPreviewAttachment] = useState<
    | (MessageAttachment & {
        previewUrl?: string;
        previewText?: string;
        contentType?: string;
        previewError?: string;
      })
    | undefined
  >();
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    return () => {
      if (previewAttachment?.previewUrl?.startsWith("blob:"))
        URL.revokeObjectURL(previewAttachment.previewUrl);
    };
  }, [previewAttachment?.previewUrl]);

  const openAttachment = async (attachment: MessageAttachment) => {
    const next = {
      ...attachment,
      contentType: attachment.content_type,
      previewText: attachment.extracted_text,
      previewUrl: attachment.public_url ?? attachment.url,
    };
    setPreviewAttachment(next);
    const fileId = attachment.file_id ?? attachment.id;
    if (
      !fileId ||
      attachment.extracted_text ||
      attachment.public_url ||
      attachment.url
    )
      return;
    setPreviewLoading(true);
    try {
      const preview = await api.previewFile(fileId);
      setPreviewAttachment((current) =>
        current ? { ...current, ...preview } : current,
      );
    } catch (error) {
      setPreviewAttachment((current) =>
        current
          ? {
              ...current,
              previewError:
                error instanceof Error ? error.message : "附件预览失败",
            }
          : current,
      );
    } finally {
      setPreviewLoading(false);
    }
  };

  if (isEvent) {
    return (
      <div className="event-message">
        <Tag icon={<BranchesOutlined />}>{message.author}</Tag>
        <Text type="secondary">{message.content}</Text>
      </div>
    );
  }

  if (message.kind === "preview_card") {
    return (
      <div className="message-row from-agent">
        <Avatar className="message-avatar">{message.author.slice(0, 1)}</Avatar>
        <button
          className="message-card preview-message-card preview-card-button"
          data-testid="preview-card"
          onClick={() => onPreview(message)}
        >
          <Flex justify="space-between" align="center">
            <Space>
              <EyeOutlined />
              <Text strong>{message.content}</Text>
            </Space>
            <Tag color="blue">预览产物</Tag>
          </Flex>
          <Paragraph type="secondary">
            产物已生成，点击打开右侧预览、编辑、Diff 对比和部署。
          </Paragraph>
        </button>
      </div>
    );
  }

  const previewType =
    previewAttachment?.contentType ?? previewAttachment?.content_type ?? "";
  const previewUrl =
    previewAttachment?.previewUrl ??
    previewAttachment?.public_url ??
    previewAttachment?.url;

  return (
    <>
      <div className={`message-row ${isUser ? "from-user" : "from-agent"}`}>
        <Avatar className="message-avatar">{message.author.slice(0, 1)}</Avatar>
        <div className="message-card">
          <Flex justify="space-between" align="center" gap={12}>
            <Space>
              <Text strong>{message.author}</Text>
              <Tag>{message.kind}</Tag>
              {message.streamState === "streaming" && (
                <Tag color="processing">流式生成中</Tag>
              )}
            </Space>
            <Text type="secondary" className="time">
              {formatTime(message.createdAt)}
            </Text>
          </Flex>
          {quoted && <div className="quote-block">{quoted.content}</div>}
          <div className="message-content">
            <MarkdownContent text={message.content} />
          </div>
          {attachments.length > 0 && (
            <div
              className="message-attachments"
              data-testid="message-attachments"
            >
              {attachments.map((file) => (
                <button
                  type="button"
                  key={file.file_id ?? file.id ?? attachmentName(file)}
                  className="message-attachment"
                  onClick={() => openAttachment(file)}
                  data-testid="message-attachment-preview"
                >
                  <CloudUploadOutlined />
                  <span className="message-attachment-name">
                    {attachmentName(file)}
                  </span>
                  <span className="message-attachment-meta">
                    {formatFileSize(file.size)} ·{" "}
                    {file.parse_status ?? "stored"}
                  </span>
                </button>
              ))}
            </div>
          )}
          <Space>
            <Tooltip title="引用">
              <Button
                size="small"
                icon={<MessageOutlined />}
                onClick={() => onQuote(message)}
              />
            </Tooltip>
            <Tooltip title="复制">
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={() =>
                  onCopy(stripInternalAgentOutput(message.content))
                }
              />
            </Tooltip>
            {!isUser && (
              <Tooltip title="重新生成">
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={() => onRegenerate(message)}
                />
              </Tooltip>
            )}
          </Space>
        </div>
      </div>
      <Modal
        title={
          previewAttachment
            ? `附件预览：${attachmentName(previewAttachment)}`
            : "附件预览"
        }
        open={Boolean(previewAttachment)}
        onCancel={() => setPreviewAttachment(undefined)}
        footer={
          <Space>
            <Button
              onClick={() => setPreviewAttachment(undefined)}
              data-testid="attachment-preview-close"
            >
              关闭
            </Button>
            {previewUrl && (
              <Button href={previewUrl} target="_blank">
                打开原文件
              </Button>
            )}
          </Space>
        }
      >
        <div
          className="attachment-preview"
          data-testid="attachment-preview-modal"
        >
          {previewAttachment && (
            <Space
              direction="vertical"
              size={2}
              className="attachment-preview-meta"
            >
              <Text strong>{attachmentName(previewAttachment)}</Text>
              <Text type="secondary">
                {previewType || "未知类型"} ·{" "}
                {formatFileSize(previewAttachment.size)}
              </Text>
            </Space>
          )}
          {previewLoading ? (
            <Spin />
          ) : previewAttachment?.previewError ? (
            <Text type="danger">{previewAttachment.previewError}</Text>
          ) : previewAttachment?.previewText ? (
            <pre>{previewAttachment.previewText}</pre>
          ) : previewUrl && previewType.startsWith("image/") ? (
            <img
              src={previewUrl}
              alt={
                previewAttachment ? attachmentName(previewAttachment) : "附件"
              }
            />
          ) : previewUrl && previewType.includes("pdf") ? (
            <iframe
              title={
                previewAttachment ? attachmentName(previewAttachment) : "附件"
              }
              src={previewUrl}
            />
          ) : (
            <Space direction="vertical">
              <Text strong>
                {previewAttachment && attachmentName(previewAttachment)}
              </Text>
              <Text type="secondary">
                {previewType || "未知类型"} ·{" "}
                {formatFileSize(previewAttachment?.size)}
              </Text>
              <Text type="secondary">
                后端未返回可直接渲染的内容，可从文件资产或原文件入口查看。
              </Text>
            </Space>
          )}
        </div>
      </Modal>
    </>
  );
}

function ChatPanel({
  user,
  active,
  messages,
  loading,
  streamState,
  onSend,
  onRegenerate,
  onOpenMembers,
  onOpenSettings,
  onUploadFile,
  onOpenPreview,
  onStopStreaming,
}: {
  user: User;
  active?: Conversation;
  messages: ChatMessage[];
  loading: boolean;
  streamState: "idle" | "streaming" | "done" | "error";
  onSend: (
    text: string,
    quoted?: ChatMessage,
    attachments?: UploadedFile[],
  ) => void;
  onRegenerate: (message: ChatMessage) => void;
  onOpenMembers: () => void;
  onOpenSettings: () => void;
  onUploadFile: (file: File) => Promise<UploadedFile>;
  onOpenPreview: (message: ChatMessage) => void;
  onStopStreaming: () => void;
}) {
  const [text, setText] = useState("");
  const [quoted, setQuoted] = useState<ChatMessage>();
  const [pendingFiles, setPendingFiles] = useState<UploadedFile[]>([]);
  const { message } = AntApp.useApp();

  const submit = () => {
    const value =
      text.trim() || (pendingFiles.length ? "请结合上传附件继续处理。" : "");
    if (!value || !active) return;
    onSend(value, quoted, pendingFiles);
    setText("");
    setQuoted(undefined);
    setPendingFiles([]);
  };

  const copy = async (value: string) => {
    await navigator.clipboard.writeText(value);
    message.success("已复制");
  };

  const participantAvatars = active?.participants.slice(0, 8) ?? [];

  return (
    <Content className="chat-panel">
      <Header className="chat-header">
        <div>
          <Space align="center" wrap>
            <Title level={3}>{active?.title ?? "选择会话"}</Title>
            {active?.chat_type === "group" && (
              <Tag color="blue">
                {active.agent_count ?? active.participants.length}/8 Agent
              </Tag>
            )}
            {active?.master_enabled && <Tag color="green">主控调度</Tag>}
          </Space>
          <Space size={4} wrap className="participant-strip">
            {participantAvatars.map((item) => (
              <Tooltip
                title={`${participantName(item)} · ${item.role ?? "member"}`}
                key={item.id ?? item.agent_id}
              >
                <Avatar
                  size="small"
                  style={{
                    background:
                      item.agent_status === "offline" ? "#9ca3af" : "#1677ff",
                  }}
                >
                  {participantName(item).slice(0, 1)}
                </Avatar>
              </Tooltip>
            ))}
            {active?.chat_type === "group" && (
              <>
                <Button
                  size="small"
                  icon={<UserAddOutlined />}
                  onClick={onOpenMembers}
                  data-testid="conversation-members"
                >
                  成员
                </Button>
                <Button
                  size="small"
                  icon={<BranchesOutlined />}
                  onClick={onOpenSettings}
                  data-testid="conversation-settings"
                >
                  群聊设置
                </Button>
              </>
            )}
          </Space>
        </div>
        <Space>
          {streamState === "streaming" && <Spin size="small" />}
          <Avatar>{user.avatar ?? user.name.slice(0, 1)}</Avatar>
        </Space>
      </Header>
      <div className="message-list">
        {loading ? (
          <Spin />
        ) : messages.length ? (
          messages.map((item) => (
            <MessageBubble
              key={item.id}
              message={item}
              quoted={messages.find(
                (messageItem) => messageItem.id === item.quotedMessageId,
              )}
              onQuote={setQuoted}
              onRegenerate={onRegenerate}
              onCopy={copy}
              onPreview={onOpenPreview}
            />
          ))
        ) : (
          <Empty description="暂无消息" />
        )}
      </div>
      <div className="composer">
        {quoted && (
          <div className="composer-quote">
            <Text type="secondary" ellipsis>
              引用：{quoted.content}
            </Text>
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
        <TextArea
          data-testid="message-input"
          aria-label="message-input"
          autoSize={{ minRows: 2, maxRows: 6 }}
          value={text}
          placeholder="输入消息，支持 @Agent 指定响应；Enter 发送，Shift+Enter 换行"
          onChange={(event) => setText(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <Flex justify="space-between" align="center">
          <Space>
            <Upload
              showUploadList={false}
              customRequest={async (options: UploadRequestOption) => {
                const uploaded = await onUploadFile(options.file as File);
                setPendingFiles((current) => [uploaded, ...current]);
                options.onSuccess?.("ok");
              }}
            >
              <Button icon={<CloudUploadOutlined />} data-testid="file-upload">
                上传文件
              </Button>
            </Upload>
          </Space>
          {streamState === "streaming" ? (
            <Button danger icon={<ReloadOutlined />} onClick={onStopStreaming}>
              Stop
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={submit}
              disabled={!active}
              data-testid="send-message"
            >
              发送
            </Button>
          )}
        </Flex>
      </div>
    </Content>
  );
}

function AgentDirectoryDrawer({
  open,
  agents,
  onClose,
  onRefresh,
  onCreateAgent,
  onUpdateAgent,
  onDeleteAgent,
  onTestAgent,
}: {
  open: boolean;
  agents: Agent[];
  onClose: () => void;
  onRefresh: () => void;
  onCreateAgent: (agent: Agent) => void;
  onUpdateAgent: (agent: Agent) => void;
  onDeleteAgent: (agent: Agent) => Promise<void>;
  onTestAgent: (agentId: string, text: string) => Promise<string>;
}) {
  const [query, setQuery] = useState("");
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [capabilityText, setCapabilityText] = useState("");
  const [capabilities, setCapabilities] = useState<AgentCapability[]>([]);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [testAgent, setTestAgent] = useState<Agent>();
  const [editingAgent, setEditingAgent] = useState<Agent>();
  const [testText, setTestText] = useState("请用三点说明你的能力。");
  const [testResult, setTestResult] = useState("");
  const [testLoading, setTestLoading] = useState(false);
  const [testError, setTestError] = useState("");
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [toolCatalog, setToolCatalog] = useState<ToolDefinition[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const { message } = AntApp.useApp();

  useEffect(() => {
    if (!open) return;
    Promise.all([
      api.modelConfigs().catch(() => []),
      api.tools().catch(() => []),
      api.skills().catch(() => []),
      api.mcpServers().catch(() => []),
    ]).then(([configs, tools, nextSkills, servers]) => {
      setModelConfigs(configs);
      setToolCatalog(tools);
      setSkills(nextSkills);
      setMcpServers(servers);
    });
  }, [open]);

  const toolOptions = toolCatalog.map((tool) => ({
    label: `${tool.display_name ?? tool.name} · ${tool.name}`,
    value: tool.name,
  }));
  const skillOptions = skills.map((skill) => ({
    label: `${skill.name} · ${skill.category}`,
    value: skill.id,
  }));
  const mcpOptions = mcpServers.map((server) => ({
    label: `${server.name} · ${server.transport}`,
    value: server.id,
  }));
  const modelConfigOptions = modelConfigs.map((model) => ({
    label: `${model.name} · ${model.model_id}`,
    value: model.id,
  }));
  const modelLabel = (modelConfigId?: string) => {
    const model =
      modelConfigs.find((item) => item.id === modelConfigId) ??
      (!modelConfigId ? modelConfigs[0] : undefined);
    return model ? `${model.name} · ${model.model_id}` : "火山方舟默认模型";
  };

  const visible = agents.filter((agent) => {
    const text =
      `${agent.name} ${agent.description} ${agent.capabilities.map((item) => item.label).join(" ")}`.toLowerCase();
    return text.includes(query.toLowerCase());
  });

  const seedAgentDraftFromBrief = (brief: string) => {
    const value = brief.trim();
    if (!value) return;
    const compact = value
      .replace(/\s+/g, "")
      .replace(/[，。,.]/g, "")
      .slice(0, 14);
    const prompt = `你是${value}。请保持结构化、可验证、可执行，并在需要时调用已授权工具。`;
    if (!form.getFieldValue("name"))
      form.setFieldsValue({ name: `${compact || "自定义"} Agent` });
    if (!form.getFieldValue("description"))
      form.setFieldsValue({ description: value.slice(0, 180) });
    if (!form.getFieldValue("system_prompt")) {
      setSystemPrompt(prompt);
      form.setFieldsValue({ system_prompt: prompt });
    }
    if (!capabilities.length) {
      setCapabilities([
        { label: "任务分析", category: "通用", proficiency: 4 },
        { label: "结构化输出", category: "通用", proficiency: 4 },
      ]);
    }
  };

  const parseCapabilities = async () => {
    const text = String(
      form.getFieldValue("capability_text") ?? capabilityText ?? "",
    );
    const parsed = await api.parseCapabilities(text);
    setCapabilities(parsed.items);
    setSystemPrompt(parsed.system_prompt);
    form.setFieldsValue({ system_prompt: parsed.system_prompt });
  };

  const generateAgentDraft = async () => {
    const name = String(form.getFieldValue("name") ?? "");
    const description = String(form.getFieldValue("description") ?? "");
    const capabilityBrief = String(
      form.getFieldValue("capability_text") ?? capabilityText ?? "",
    );
    const brief = [name, description, capabilityBrief]
      .filter(Boolean)
      .join("\n");
    if (!brief.trim()) {
      message.warning("先输入 Agent 目标或职责描述");
      return;
    }
    const generated = await api.generateAgentConfig(
      brief,
      form.getFieldValue("base_agent_id"),
      form.getFieldValue("tools") ?? [],
    );
    setCapabilities(generated.capabilities);
    setSystemPrompt(generated.system_prompt);
    setCapabilityText(generated.capability_text ?? capabilityBrief);
    form.setFieldsValue({
      name: generated.name,
      description: generated.description,
      capability_text: generated.capability_text ?? capabilityBrief,
      system_prompt: generated.system_prompt,
      tools: generated.tools,
      temperature:
        generated.temperature ?? Number(generated.config?.temperature ?? 0.7),
    });
    message.success("AI 已生成 Agent 配置草稿");
  };

  const openEditAgent = (agent: Agent) => {
    setEditingAgent(agent);
    editForm.setFieldsValue({
      name: agent.name,
      display_name: agent.display_name,
      description: agent.description,
      status: agent.status,
      system_prompt: agent.config.custom_prompt_prefix,
      model_config_id: agent.config.model_config_id,
      tools: agent.config.tools ?? [],
      skill_ids: agent.config.skill_ids ?? [],
      mcp_server_ids: agent.config.mcp_server_ids ?? [],
      agentic_loop_enabled:
        agent.config.agentic_loop?.enabled ??
        Boolean(
          (agent.config.tools ?? []).length ||
          (agent.config.skill_ids ?? []).length ||
          (agent.config.mcp_server_ids ?? []).length,
        ),
      agentic_loop_steps: agent.config.agentic_loop?.max_steps ?? 2,
      temperature: agent.config.temperature ?? 0.7,
    });
  };

  const saveEditAgent = async () => {
    if (!editingAgent) return;
    const values = await editForm.validateFields();
    const updated = await api.updateAgent(editingAgent.id, {
      name: values.name,
      display_name: values.display_name,
      description: values.description,
      status: values.status,
      system_prompt: values.system_prompt,
      tools: values.tools ?? [],
      config: {
        temperature: values.temperature ?? 0.7,
        model_config_id: values.model_config_id,
        skill_ids: values.skill_ids ?? [],
        mcp_server_ids: values.mcp_server_ids ?? [],
        agentic_loop: {
          enabled: Boolean(values.agentic_loop_enabled),
          max_steps: values.agentic_loop_steps ?? 2,
          tool_policy: values.agentic_loop_enabled
            ? "agent_permissions"
            : "chat_only",
        },
      },
    });
    onUpdateAgent(updated);
    setEditingAgent(undefined);
    message.success("Agent 已更新");
  };

  const submit = async () => {
    const values = await form.validateFields();
    const created = await api.createAgent({
      name: values.name,
      description: values.description,
      capabilities,
      system_prompt: values.system_prompt,
      base_agent_id: values.base_agent_id,
      model_config_id: values.model_config_id,
      tools: values.tools ?? [],
      skill_ids: values.skill_ids ?? [],
      mcp_server_ids: values.mcp_server_ids ?? [],
      config: {
        temperature: values.temperature ?? 0.7,
        model_config_id: values.model_config_id,
        skill_ids: values.skill_ids ?? [],
        mcp_server_ids: values.mcp_server_ids ?? [],
        agentic_loop: {
          enabled: Boolean(values.agentic_loop_enabled),
          max_steps: values.agentic_loop_steps ?? 2,
          tool_policy: values.agentic_loop_enabled
            ? "agent_permissions"
            : "chat_only",
        },
      },
    });
    onCreateAgent(created);
    setCreatorOpen(false);
    message.success("自定义 Agent 已发布");
  };

  return (
    <>
      <Drawer
        width={720}
        title="Agent 广场与通讯录"
        open={open}
        onClose={onClose}
      >
        <Flex justify="space-between" align="center" className="drawer-toolbar">
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索名称、能力、描述"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Space>
            <Button onClick={onRefresh}>刷新状态</Button>
            <Button
              type="primary"
              icon={<RobotOutlined />}
              onClick={() => setCreatorOpen(true)}
              data-testid="create-agent"
            >
              创建自定义 Agent
            </Button>
          </Space>
        </Flex>
        <List
          grid={{ gutter: 12, column: 1 }}
          dataSource={visible}
          renderItem={(agent) => (
            <List.Item>
              <Card className="agent-card">
                <Flex justify="space-between" align="start">
                  <Space align="start">
                    <Badge
                      status={
                        agent.status === "online"
                          ? "success"
                          : agent.status === "degraded"
                            ? "warning"
                            : "default"
                      }
                      dot
                    >
                      <Avatar
                        style={{ background: agent.avatar_color ?? "#1677ff" }}
                      >
                        {agent.name.slice(0, 1)}
                      </Avatar>
                    </Badge>
                    <div>
                      <Space>
                        <Text strong>{agent.display_name ?? agent.name}</Text>
                        {agent.is_official && <Tag color="blue">官方</Tag>}
                        <Tag>{agent.type}</Tag>
                      </Space>
                      <Paragraph type="secondary" ellipsis={{ rows: 2 }}>
                        {agent.description}
                      </Paragraph>
                    </div>
                  </Space>
                  <Tag
                    color={agent.status === "online" ? "success" : "default"}
                  >
                    {agent.status}
                  </Tag>
                </Flex>
                <Space size={[4, 4]} wrap>
                  {agent.capabilities.slice(0, 4).map((cap) => (
                    <Tag key={cap.label}>
                      {cap.label}·{cap.proficiency}
                    </Tag>
                  ))}
                </Space>
                <Space size={[4, 4]} wrap className="mt-8">
                  {(agent.config.tools ?? []).slice(0, 5).map((tool) => (
                    <Tag key={tool} color="geekblue">
                      {tool}
                    </Tag>
                  ))}
                  {(agent.config.skill_ids ?? []).length > 0 && (
                    <Tag color="cyan">
                      {agent.config.skill_ids?.length} Skills
                    </Tag>
                  )}
                  {(agent.config.mcp_server_ids ?? []).length > 0 && (
                    <Tag color="gold">
                      {agent.config.mcp_server_ids?.length} MCP
                    </Tag>
                  )}
                  {agent.config.agentic_loop?.enabled === false && (
                    <Tag>纯对话</Tag>
                  )}
                  <Tag color="purple">
                    模型：{modelLabel(agent.config.model_config_id)}
                  </Tag>
                </Space>
                <Divider />
                <Flex justify="space-between">
                  <Text type="secondary">
                    {agent.response_latency_ms}ms · {agent.provider}
                  </Text>
                  <Space>
                    <Button
                      size="small"
                      onClick={() => {
                        setTestAgent(agent);
                        setTestResult("");
                        setTestError("");
                      }}
                    >
                      测试
                    </Button>
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => openEditAgent(agent)}
                      data-testid={`edit-agent-${agent.id}`}
                    >
                      编辑
                    </Button>
                    {!agent.is_official && (
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        data-testid={`delete-agent-${agent.id}`}
                        onClick={() => {
                          Modal.confirm({
                            title: `删除 Agent：${agent.name}`,
                            content:
                              "删除后不会再出现在 Agent 广场，也不能加入新会话。",
                            okText: "删除",
                            okButtonProps: { danger: true },
                            onOk: async () => {
                              await onDeleteAgent(agent);
                              message.success("Agent 已删除");
                            },
                          });
                        }}
                      />
                    )}
                  </Space>
                </Flex>
              </Card>
            </List.Item>
          )}
        />
      </Drawer>

      <Modal
        title="创建自定义 Agent"
        width={760}
        open={creatorOpen}
        onCancel={() => setCreatorOpen(false)}
        onOk={submit}
        okText="发布"
        okButtonProps={{ "data-testid": "agent-publish" }}
      >
        <Steps
          size="small"
          current={2}
          items={[
            { title: "基础信息" },
            { title: "能力解析" },
            { title: "提示词" },
            { title: "模型工具" },
            { title: "测试发布" },
          ]}
        />
        <Form
          form={form}
          layout="vertical"
          className="agent-form"
          initialValues={{
            temperature: 0.7,
            tools: ["file.read", "file.write", "file.extract_text"],
            skill_ids: [],
            mcp_server_ids: [],
            agentic_loop_enabled: true,
            agentic_loop_steps: 2,
          }}
          onValuesChange={(changed) => {
            if ("capability_text" in changed)
              setCapabilityText(String(changed.capability_text ?? ""));
            if ("system_prompt" in changed)
              setSystemPrompt(String(changed.system_prompt ?? ""));
          }}
        >
          <Form.Item
            name="name"
            label="Agent 名称"
            rules={[{ required: true, message: "请输入 Agent 名称" }]}
          >
            <Input maxLength={30} placeholder="数据库设计专家" />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
            rules={[{ required: true, message: "请输入描述" }]}
          >
            <TextArea rows={2} maxLength={500} />
          </Form.Item>
          <Form.Item name="capability_text" label="自然语言能力描述">
            <TextArea
              onChange={(event) => {
                setCapabilityText(event.target.value);
                seedAgentDraftFromBrief(event.target.value);
              }}
              onInput={(event) => {
                setCapabilityText(event.currentTarget.value);
                seedAgentDraftFromBrief(event.currentTarget.value);
              }}
              rows={3}
              data-testid="agent-capability-text"
            />
            <Space className="mt-8">
              <Button icon={<ToolOutlined />} onClick={parseCapabilities}>
                AI 解析能力标签
              </Button>
              <Button
                icon={<RobotOutlined />}
                onClick={generateAgentDraft}
                data-testid="ai-generate-agent"
              >
                AI 生成 Agent
              </Button>
            </Space>
          </Form.Item>
          <Space size={[4, 4]} wrap>
            {capabilities.map((cap) => (
              <Tag key={cap.label}>
                {cap.label} · {cap.category} · {cap.proficiency}
              </Tag>
            ))}
          </Space>
          <Form.Item
            name="system_prompt"
            label="系统提示词"
            rules={[{ required: true, message: "请配置系统提示词" }]}
          >
            <TextArea
              rows={5}
              value={systemPrompt}
              onChange={(event) => setSystemPrompt(event.target.value)}
              data-testid="agent-system-prompt"
            />
          </Form.Item>
          <Form.Item name="base_agent_id" label="继承基础 Agent（可选）">
            <Select
              allowClear
              options={agents.map((agent) => ({
                label: agent.name,
                value: agent.id,
              }))}
            />
          </Form.Item>
          <Form.Item name="model_config_id" label="底层模型配置">
            <Select
              allowClear
              placeholder="使用系统默认豆包模型"
              options={modelConfigOptions}
            />
          </Form.Item>
          <Form.Item name="tools" label="工具权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择该 Agent 可调用的工具"
              optionFilterProp="label"
              options={toolOptions}
            />
          </Form.Item>
          <Form.Item name="skill_ids" label="Skill 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 Skills"
              optionFilterProp="label"
              options={skillOptions}
            />
          </Form.Item>
          <Form.Item name="mcp_server_ids" label="MCP 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 MCP 服务"
              optionFilterProp="label"
              options={mcpOptions}
            />
          </Form.Item>
          <Space align="start">
            <Form.Item
              name="agentic_loop_enabled"
              label="小循环模式"
              valuePropName="checked"
            >
              <Checkbox>允许短 Agentic Loop</Checkbox>
            </Form.Item>
            <Form.Item name="agentic_loop_steps" label="最大步数">
              <Select
                style={{ width: 120 }}
                options={[
                  { label: "1 步", value: 1 },
                  { label: "2 步", value: 2 },
                  { label: "3 步", value: 3 },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="temperature" label="Temperature">
            <Select
              options={[
                { label: "0.2 稳定", value: 0.2 },
                { label: "0.7 平衡", value: 0.7 },
                { label: "1.2 发散", value: 1.2 },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`编辑 Agent：${editingAgent?.name ?? ""}`}
        width={720}
        open={Boolean(editingAgent)}
        onCancel={() => setEditingAgent(undefined)}
        onOk={saveEditAgent}
        okText="保存"
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label="Agent 名称"
            rules={[{ required: true }]}
          >
            <Input maxLength={30} />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input maxLength={30} />
          </Form.Item>
          <Form.Item
            name="description"
            label="描述"
            rules={[{ required: true }]}
          >
            <TextArea rows={3} maxLength={500} />
          </Form.Item>
          <Form.Item
            name="system_prompt"
            label="系统提示词"
            rules={[{ required: true }]}
          >
            <TextArea rows={5} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select
              options={[
                { label: "online", value: "online" },
                { label: "offline", value: "offline" },
                { label: "degraded", value: "degraded" },
                { label: "maintenance", value: "maintenance" },
              ]}
            />
          </Form.Item>
          <Form.Item name="model_config_id" label="底层模型配置">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="使用系统默认豆包模型"
              options={modelConfigOptions}
            />
          </Form.Item>
          <Form.Item name="tools" label="工具权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择该 Agent 可调用的工具"
              optionFilterProp="label"
              options={toolOptions}
            />
          </Form.Item>
          <Form.Item name="skill_ids" label="Skill 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 Skills"
              optionFilterProp="label"
              options={skillOptions}
            />
          </Form.Item>
          <Form.Item name="mcp_server_ids" label="MCP 权限">
            <Select
              mode="multiple"
              showSearch
              placeholder="选择可调用的 MCP 服务"
              optionFilterProp="label"
              options={mcpOptions}
            />
          </Form.Item>
          <Space align="start">
            <Form.Item
              name="agentic_loop_enabled"
              label="小循环模式"
              valuePropName="checked"
            >
              <Checkbox>允许短 Agentic Loop</Checkbox>
            </Form.Item>
            <Form.Item name="agentic_loop_steps" label="最大步数">
              <Select
                style={{ width: 120 }}
                options={[
                  { label: "1 步", value: 1 },
                  { label: "2 步", value: 2 },
                  { label: "3 步", value: 3 },
                ]}
              />
            </Form.Item>
          </Space>
          <Form.Item name="temperature" label="Temperature">
            <Select
              options={[
                { label: "0.2 稳定", value: 0.2 },
                { label: "0.7 平衡", value: 0.7 },
                { label: "1.2 发散", value: 1.2 },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={`测试 Agent：${testAgent?.name ?? ""}`}
        open={Boolean(testAgent)}
        onCancel={() => setTestAgent(undefined)}
        footer={null}
      >
        <Space direction="vertical" className="full-width">
          <TextArea
            value={testText}
            onChange={(event) => setTestText(event.target.value)}
            rows={3}
          />
          <Button
            type="primary"
            loading={testLoading}
            onClick={async () => {
              if (!testAgent) return;
              setTestLoading(true);
              setTestError("");
              setTestResult("正在等待模型回复...");
              try {
                setTestResult(await onTestAgent(testAgent.id, testText));
              } catch (error) {
                setTestResult("");
                setTestError(
                  error instanceof Error ? error.message : "连接失败",
                );
              } finally {
                setTestLoading(false);
              }
            }}
          >
            发送测试
          </Button>
          {testLoading && (
            <Text type="secondary">
              正在等待回复，真实模型可能需要几秒钟...
            </Text>
          )}
          {testError && (
            <Card className="result-box error-box">连接失败：{testError}</Card>
          )}
          {testResult && <Card>{testResult}</Card>}
        </Space>
      </Modal>
    </>
  );
}

function CreateConversationModal({
  open,
  group,
  agents,
  categoryOptions,
  onCancel,
  onCreate,
}: {
  open: boolean;
  group: boolean;
  agents: Agent[];
  categoryOptions: string[];
  onCancel: () => void;
  onCreate: (payload: {
    title?: string;
    agentIds: string[];
    group: boolean;
    masterEnabled: boolean;
    folder: string;
  }) => void;
}) {
  const [form] = Form.useForm();
  const onlineAgents = agents.filter((agent) => agent.status === "online");
  const categorySelectOptions = categoryOptions.map((name) => ({
    label: name,
    value: name,
  }));
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!open) {
      initializedRef.current = false;
      form.resetFields();
      return;
    }
    if (initializedRef.current) return;
    initializedRef.current = true;
    form.setFieldsValue({
      agentIds: group
        ? onlineAgents
            .slice(0, Math.min(4, onlineAgents.length))
            .map((agent) => agent.id)
        : [],
      masterEnabled: true,
      folder: "Default",
    });
  }, [open, group, onlineAgents, form]);

  const submit = async () => {
    const values = await form.validateFields();
    onCreate({
      title: values.title,
      agentIds: values.agentIds,
      group,
      masterEnabled: values.masterEnabled ?? true,
      folder: normalizeConversationCategory(values.folder),
    });
    form.resetFields();
  };

  return (
    <Modal
      title={group ? "新建多 Agent 群聊" : "新建 Agent 单聊"}
      open={open}
      onCancel={onCancel}
      onOk={submit}
      okText="创建"
      okButtonProps={{ "data-testid": "create-conversation-confirm" }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ masterEnabled: true, folder: "Default" }}
      >
        <Form.Item name="title" label="会话名称">
          <Input
            placeholder={group ? "多 Agent 协作-答辩演示" : "Agent 单聊"}
          />
        </Form.Item>
        <Form.Item name="folder" label="分类/文件夹">
          <Select options={categorySelectOptions} placeholder="选择左侧分类" />
        </Form.Item>
        <Form.Item
          name="agentIds"
          label={group ? "选择 2-8 个 Agent" : "选择 1 个 Agent"}
          rules={[
            {
              validator: async (_, value?: string[]) => {
                const count = value?.length ?? 0;
                if (group && (count < 2 || count > 8))
                  throw new Error("群聊需要选择 2-8 个 Agent");
                if (!group && count !== 1)
                  throw new Error("单聊需要选择 1 个 Agent");
              },
            },
          ]}
        >
          <Select
            data-testid="agent-select"
            mode="multiple"
            maxCount={group ? 8 : 1}
            placeholder="从 Agent 通讯录选择"
            options={onlineAgents.map((agent) => ({
              label: `${agent.name} · ${agent.capabilities
                .slice(0, 2)
                .map((cap) => cap.label)
                .join("/")}`,
              value: agent.id,
            }))}
          />
        </Form.Item>
        {group && (
          <Form.Item name="masterEnabled" valuePropName="checked">
            <Checkbox>启用主控 Agent 自动拆解和调度</Checkbox>
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
}

function MembersDrawer({
  open,
  active,
  agents,
  onClose,
  onAddAgents,
  onRemoveParticipant,
}: {
  open: boolean;
  active?: Conversation;
  agents: Agent[];
  onClose: () => void;
  onAddAgents: (ids: string[]) => void;
  onRemoveParticipant: (
    participant: Conversation["participants"][number],
  ) => Promise<void>;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const isGroup = active?.chat_type === "group";
  const existing = new Set(
    active?.participants.map((item) => item.agent_id).filter(Boolean),
  );
  const removableAgentCount =
    active?.participants.filter((item) => item.participant_type === "agent")
      .length ?? 0;
  const options = agents
    .filter((agent) => !existing.has(agent.id) && agent.status === "online")
    .map((agent) => ({
      label: `${agent.name} · ${agent.type}`,
      value: agent.id,
    }));

  return (
    <Drawer title="群聊成员与邀请" width={460} open={open} onClose={onClose}>
      <Statistic
        title="当前 Agent 人数"
        value={active?.agent_count ?? active?.participants.length ?? 0}
        suffix="/8"
      />
      <List
        className="member-list"
        dataSource={active?.participants ?? []}
        renderItem={(item) => (
          <List.Item
            actions={[
              item.participant_type === "agent" && removableAgentCount <= 1 ? (
                <Tooltip key="last-agent" title="至少保留 1 个 Agent">
                  <Button
                    size="small"
                    shape="circle"
                    icon={<DeleteOutlined />}
                    disabled
                  />
                </Tooltip>
              ) : (
                <Tooltip key="remove" title="移除成员">
                  <Button
                    size="small"
                    danger
                    shape="circle"
                    icon={<DeleteOutlined />}
                    onClick={() => {
                      Modal.confirm({
                        title: `移除成员：${participantName(item)}`,
                        content:
                          "移除后该 Agent 不再参与当前群聊，默认工作流也会同步刷新。",
                        okText: "移除",
                        okButtonProps: { danger: true },
                        onOk: () => onRemoveParticipant(item),
                      });
                    }}
                  />
                </Tooltip>
              ),
            ]}
          >
            <List.Item.Meta
              avatar={<Avatar>{participantName(item).slice(0, 1)}</Avatar>}
              title={
                <Space>
                  <Text strong>{participantName(item)}</Text>
                  <Tag>{item.role ?? "member"}</Tag>
                </Space>
              }
              description={`${item.participant_type ?? "agent"} · ${item.agent_status ?? "active"}`}
            />
          </List.Item>
        )}
      />
      <Divider />
      {isGroup ? (
        <>
          <Text strong>邀请 Agent 加入</Text>
          <Select
            mode="multiple"
            className="full-width mt-8"
            options={options}
            value={selected}
            onChange={setSelected}
            placeholder="选择要加入的 Agent"
          />
          <Button
            className="mt-8"
            type="primary"
            disabled={!selected.length}
            onClick={() => {
              onAddAgents(selected);
              setSelected([]);
            }}
          >
            加入群聊
          </Button>
        </>
      ) : (
        <Text type="secondary">
          单聊只保留一个 Agent；需要多人协作时请创建多 Agent 群聊。
        </Text>
      )}
    </Drawer>
  );
}

function ConversationSettingsDrawer({
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
  const [draggingNodeId, setDraggingNodeId] = useState<string>();
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
  const workflowEdges = workflow?.edges ?? [];
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
    setWorkflow(next);
    setWorkflowJson(JSON.stringify(next, null, 2));
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
    setWorkflow(nextWorkflow);
    setWorkflowJson(JSON.stringify(nextWorkflow, null, 2));
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

  const workflowIcon = (type?: string, role?: string) => {
    if (type === "start") return <MessageOutlined />;
    if (type === "tool" || type === "mcp" || type === "skill")
      return <ToolOutlined />;
    if (type === "condition" || type === "loop" || role === "master")
      return <BranchesOutlined />;
    if (type === "review" || role === "reviewer")
      return <CheckCircleOutlined />;
    if (type === "artifact" || type === "end" || role === "artifact")
      return <RocketOutlined />;
    return <RobotOutlined />;
  };

  const reorderWorkflowNode = (sourceId: string, targetId: string) => {
    if (!workflow || sourceId === targetId) return;
    const nodes = [...workflow.nodes];
    const from = nodes.findIndex((node) => node.id === sourceId);
    const to = nodes.findIndex((node) => node.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = nodes.splice(from, 1);
    nodes.splice(to, 0, moved);
    setWorkflowDraft({ ...workflow, nodes });
  };

  const addWorkflowNode = (type: string) => {
    if (!workflow) return;
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
    if (!workflow || !editingNodeId) return;
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
    if (!active) return;
    let parsed: ConversationWorkflow;
    try {
      parsed = JSON.parse(workflowJson) as ConversationWorkflow;
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
                  {workflowNodes.length ? (
                    workflowNodes.map((node) => (
                      <div
                        key={node.id}
                        className={`workflow-node workflow-node-${node.status} workflow-node-type-${workflowNodeType(node)}`}
                        draggable
                        onClick={() => openWorkflowNodeEditor(node)}
                        onDragStart={() => setDraggingNodeId(node.id)}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={() => {
                          if (draggingNodeId)
                            reorderWorkflowNode(draggingNodeId, node.id);
                          setDraggingNodeId(undefined);
                        }}
                      >
                        <div className="workflow-node-icon">
                          {workflowIcon(workflowNodeType(node), node.role)}
                        </div>
                        <div className="workflow-node-body">
                          <Space size={4} wrap>
                            <Text strong>{node.title}</Text>
                            <Tag>
                              {WORKFLOW_NODE_TYPE_LABEL[
                                workflowNodeType(node)
                              ] ?? workflowNodeType(node)}
                            </Tag>
                          </Space>
                          <Text type="secondary" ellipsis>
                            {node.meta || node.role}
                          </Text>
                        </div>
                      </div>
                    ))
                  ) : (
                    <Empty description="当前群聊暂无 Agent 工作流" />
                  )}
                </div>
                <div className="workflow-side">
                  <Space direction="vertical" className="full-width">
                    <Space wrap>
                      <Button
                        icon={<ReloadOutlined />}
                        disabled={!active}
                        onClick={loadWorkflow}
                      >
                        重新载入
                      </Button>
                      <Button
                        icon={<RobotOutlined />}
                        disabled={!active}
                        onClick={async () => {
                          if (!active) return;
                          const generated =
                            await api.generateConversationWorkflow(
                              active.id,
                              workflowInstruction,
                            );
                          setWorkflowDraft(generated);
                          message.success("AI 已按当前群聊 Agent 生成工作流");
                        }}
                      >
                        AI 生成
                      </Button>
                      <Button
                        icon={<PlusOutlined />}
                        disabled={!workflow}
                        onClick={() => addWorkflowNode(newNodeType)}
                      >
                        添加节点
                      </Button>
                      <Button
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        disabled={!workflowJson.trim()}
                        onClick={saveWorkflow}
                      >
                        保存画布
                      </Button>
                      <Button
                        icon={<BranchesOutlined />}
                        disabled={!active || !workflow}
                        onClick={async () => {
                          if (!active || !workflow) return;
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
                      onChange={(event) =>
                        setWorkflowInstruction(event.target.value)
                      }
                      placeholder="给 AI 的画布编排意见，例如：前后端并行，Reviewer 最后审查；这个群聊只做日常问答时跳过 Master。"
                    />
                    <Select
                      value={newNodeType}
                      onChange={setNewNodeType}
                      options={WORKFLOW_NODE_TYPE_OPTIONS}
                      className="full-width"
                    />
                    <TextArea
                      rows={12}
                      value={workflowJson}
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
        open={Boolean(editingNode)}
        onCancel={() => setEditingNodeId(undefined)}
        onOk={saveWorkflowNode}
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

function GlobalSettingsDrawer({
  open,
  user,
  onClose,
  onUserUpdated,
}: {
  open: boolean;
  user: User;
  onClose: () => void;
  onUserUpdated: (user: User) => void;
}) {
  const [profileForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [providerForm] = Form.useForm();
  const [modelForm] = Form.useForm();
  const [modelProviders, setModelProviders] = useState<ModelProvider[]>([]);
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [modelTestResult, setModelTestResult] = useState("");
  const [modelTesting, setModelTesting] = useState(false);
  const { message } = AntApp.useApp();

  const loadModels = async () => {
    const [providers, configs] = await Promise.all([
      api.modelProviders(),
      api.modelConfigs(),
    ]);
    setModelProviders(providers);
    setModelConfigs(configs);
  };

  useEffect(() => {
    if (!open) return;
    profileForm.setFieldsValue({ display_name: user.name });
    loadModels().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user.id]);

  return (
    <Drawer title="全局设置" width={920} open={open} onClose={onClose}>
      <Tabs
        items={[
          {
            key: "account",
            label: "账号",
            children: (
              <div className="workspace-grid">
                <Card title="个人资料">
                  <Form
                    form={profileForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      const updated = await api.updateProfile({
                        display_name: values.display_name,
                      });
                      onUserUpdated(updated);
                      message.success("个人资料已更新");
                    }}
                  >
                    <Form.Item
                      name="display_name"
                      label="显示名称"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Button type="primary" htmlType="submit">
                      保存资料
                    </Button>
                  </Form>
                </Card>
                <Card title="修改密码">
                  <Form
                    form={passwordForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      await api.changePassword({
                        current_password: values.current_password,
                        new_password: values.new_password,
                      });
                      passwordForm.resetFields();
                      message.success("密码已更新");
                    }}
                  >
                    <Form.Item
                      name="current_password"
                      label="当前密码"
                      rules={[{ required: true }]}
                    >
                      <Input.Password />
                    </Form.Item>
                    <Form.Item
                      name="new_password"
                      label="新密码"
                      rules={[{ required: true, min: 6 }]}
                    >
                      <Input.Password />
                    </Form.Item>
                    <Button htmlType="submit">更新密码</Button>
                  </Form>
                </Card>
              </div>
            ),
          },
          {
            key: "models",
            label: "模型 API",
            children: (
              <div className="workspace-grid">
                <Card title="OpenAI 兼容供应商">
                  <Form
                    form={providerForm}
                    layout="vertical"
                    initialValues={{
                      provider_type: "openai-compatible",
                      base_url: "https://ark.cn-beijing.volces.com/api/v3",
                      default_model: "doubao-seed-2-0-lite",
                      supports_streaming: true,
                    }}
                    onFinish={async (values) => {
                      const provider = await api.createModelProvider({
                        ...values,
                        supports_streaming: Boolean(values.supports_streaming),
                        supports_embeddings: Boolean(
                          values.supports_embeddings,
                        ),
                      });
                      setModelProviders((current) => [provider, ...current]);
                      providerForm.resetFields(["name", "api_key"]);
                      await loadModels();
                      message.success("模型供应商已保存");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="我的豆包 / OpenAI 兼容模型" />
                    </Form.Item>
                    <Form.Item name="provider_type" label="类型">
                      <Select
                        options={[
                          {
                            label: "OpenAI Compatible",
                            value: "openai-compatible",
                          },
                          { label: "Volcengine Ark", value: "ark" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="base_url"
                      label="Base URL"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item name="api_key" label="API Key">
                      <Input.Password placeholder="只提交到后端，不在前端回显" />
                    </Form.Item>
                    <Form.Item
                      name="default_model"
                      label="默认模型"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Space>
                      <Form.Item
                        name="supports_streaming"
                        valuePropName="checked"
                      >
                        <Checkbox>流式</Checkbox>
                      </Form.Item>
                      <Form.Item
                        name="supports_embeddings"
                        valuePropName="checked"
                      >
                        <Checkbox>Embedding</Checkbox>
                      </Form.Item>
                    </Space>
                    <Button type="primary" htmlType="submit">
                      保存供应商
                    </Button>
                  </Form>
                </Card>
                <Card title="模型配置与真实测试">
                  <Form
                    form={modelForm}
                    layout="vertical"
                    initialValues={{
                      purpose: "chat",
                      context_window: 128000,
                      max_output_tokens: 4096,
                      temperature_default: 0.4,
                    }}
                    onFinish={async (values) => {
                      const model = await api.createModelConfig(values);
                      setModelConfigs((current) => [model, ...current]);
                      modelForm.resetFields(["name", "model_id"]);
                      message.success("模型配置已创建");
                    }}
                  >
                    <Form.Item
                      name="provider_id"
                      label="供应商"
                      rules={[{ required: true }]}
                    >
                      <Select
                        options={modelProviders.map((provider) => ({
                          label: provider.name,
                          value: provider.id,
                        }))}
                      />
                    </Form.Item>
                    <Space align="start">
                      <Form.Item
                        name="name"
                        label="名称"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="Master/Reviewer 模型" />
                      </Form.Item>
                      <Form.Item
                        name="model_id"
                        label="模型 ID"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="doubao-seed-2-0-lite" />
                      </Form.Item>
                    </Space>
                    <Space align="start">
                      <Form.Item name="purpose" label="用途">
                        <Select
                          style={{ width: 150 }}
                          options={[
                            { label: "聊天", value: "chat" },
                            { label: "主控", value: "master" },
                            { label: "Worker", value: "worker" },
                            { label: "Reviewer", value: "reviewer" },
                            { label: "摘要", value: "summary" },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item name="temperature_default" label="温度">
                        <Input type="number" step="0.1" />
                      </Form.Item>
                    </Space>
                    <Button htmlType="submit" disabled={!modelProviders.length}>
                      新增模型
                    </Button>
                  </Form>
                  <Divider />
                  <Input.Search
                    placeholder="输入测试提示词"
                    enterButton={modelTesting ? "等待中" : "测试"}
                    loading={modelTesting}
                    onSearch={async (prompt) => {
                      const currentModel = modelConfigs[0];
                      setModelTesting(true);
                      setModelTestResult("正在等待模型回复...");
                      try {
                        const result = await api.testModel(
                          prompt || "请回复模型已就绪。",
                          currentModel?.id,
                        );
                        setModelTestResult(
                          `${result.model}: ${result.response}`,
                        );
                      } catch (error) {
                        setModelTestResult(
                          `连接失败：${error instanceof Error ? error.message : "unknown"}`,
                        );
                      } finally {
                        setModelTesting(false);
                      }
                    }}
                  />
                  {modelTestResult && (
                    <div className="result-box">{modelTestResult}</div>
                  )}
                  <List
                    size="small"
                    dataSource={modelConfigs}
                    renderItem={(model) => (
                      <List.Item>
                        <List.Item.Meta
                          avatar={<Avatar icon={<ApiOutlined />} />}
                          title={
                            <Space>
                              <Text strong>{model.name}</Text>
                              <Tag>{model.purpose}</Tag>
                              <Tag>{model.status}</Tag>
                            </Space>
                          }
                          description={`${model.provider_name ?? model.provider_id} / ${model.model_id} / ${model.context_window} tokens`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
          {
            key: "general",
            label: "常规",
            children: (
              <Card>
                <Space direction="vertical">
                  <Checkbox defaultChecked>发送消息后自动滚动到底部</Checkbox>
                  <Checkbox defaultChecked>流式回复时显示运行状态</Checkbox>
                  <Checkbox defaultChecked>
                    产物卡片点击后再打开右侧预览
                  </Checkbox>
                </Space>
              </Card>
            ),
          },
        ]}
      />
    </Drawer>
  );
}

function FilesKnowledgePanel({
  files,
  knowledgeBases,
  onCreateKb,
  onImportText,
  onRetrieve,
}: {
  files: UploadedFile[];
  knowledgeBases: KnowledgeBase[];
  onCreateKb: (payload: {
    name: string;
    description: string;
    scope: string;
    visibility: string;
  }) => Promise<void>;
  onImportText: (
    kbId: string,
    payload: { title: string; content: string },
  ) => Promise<void>;
  onRetrieve: (kbId: string, query: string) => Promise<string>;
}) {
  const [kbForm] = Form.useForm();
  const [docForm] = Form.useForm();
  const [query, setQuery] = useState("");
  const [selectedKb, setSelectedKb] = useState<string>();
  const [retrieveResult, setRetrieveResult] = useState("");

  return (
    <Tabs
      items={[
        {
          key: "files",
          label: "文件",
          children: (
            <Table
              size="small"
              pagination={false}
              dataSource={files}
              rowKey="id"
              columns={[
                { title: "文件名", dataIndex: "original_filename" },
                {
                  title: "大小",
                  dataIndex: "size",
                  render: (value: number) => `${Math.ceil(value / 1024)}KB`,
                },
                {
                  title: "状态",
                  dataIndex: "parse_status",
                  render: (value: string) => <Tag>{value}</Tag>,
                },
              ]}
            />
          ),
        },
        {
          key: "knowledge",
          label: "知识库",
          children: (
            <Space direction="vertical" className="full-width">
              <Form
                form={kbForm}
                layout="vertical"
                onFinish={onCreateKb}
                initialValues={{ scope: "personal", visibility: "private" }}
              >
                <Form.Item
                  name="name"
                  label="知识库名称"
                  rules={[{ required: true }]}
                >
                  <Input
                    placeholder="项目需求知识库"
                    data-testid="knowledge-create"
                  />
                </Form.Item>
                <Form.Item name="description" label="描述">
                  <Input />
                </Form.Item>
                <Space>
                  <Form.Item name="scope" label="范围">
                    <Select
                      style={{ width: 140 }}
                      options={[
                        { label: "个人", value: "personal" },
                        { label: "工作区", value: "workspace" },
                        { label: "平台", value: "platform" },
                      ]}
                    />
                  </Form.Item>
                  <Form.Item name="visibility" label="可见性">
                    <Select
                      style={{ width: 140 }}
                      options={[
                        { label: "私有", value: "private" },
                        { label: "公开", value: "public" },
                      ]}
                    />
                  </Form.Item>
                </Space>
                <Button htmlType="submit" type="primary">
                  创建知识库
                </Button>
              </Form>
              <Divider />
              <Select
                placeholder="选择知识库"
                value={selectedKb}
                onChange={setSelectedKb}
                options={knowledgeBases.map((kb) => ({
                  label: `${kb.name} · ${kb.document_count} 文档`,
                  value: kb.id,
                }))}
                className="full-width"
              />
              <Form
                form={docForm}
                layout="vertical"
                onFinish={(values) =>
                  selectedKb && onImportText(selectedKb, values)
                }
              >
                <Form.Item
                  name="title"
                  label="导入文档标题"
                  rules={[{ required: true }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="content"
                  label="文档内容"
                  rules={[{ required: true }]}
                >
                  <TextArea rows={4} />
                </Form.Item>
                <Button disabled={!selectedKb} htmlType="submit">
                  导入并索引
                </Button>
              </Form>
              <Divider />
              <Input.Search
                placeholder="检索知识库"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onSearch={async () =>
                  selectedKb &&
                  setRetrieveResult(await onRetrieve(selectedKb, query))
                }
                enterButton="检索"
                disabled={!selectedKb}
              />
              {retrieveResult && <Card>{retrieveResult}</Card>}
            </Space>
          ),
        },
      ]}
    />
  );
}

function WorkspacesDrawer({
  open,
  workspaces,
  onClose,
  onCreateWorkspace,
  onCreateProject,
  onLoadProjects,
  onSaveProjectFile,
}: {
  open: boolean;
  workspaces: Workspace[];
  onClose: () => void;
  onCreateWorkspace: (payload: {
    name: string;
    description: string;
    type: string;
    tags: string[];
    config?: Record<string, unknown>;
  }) => Promise<void>;
  onCreateProject: (
    workspaceId: string,
    payload: { name: string; description: string; type: string },
  ) => Promise<Project>;
  onLoadProjects: (workspaceId: string) => Promise<Project[]>;
  onSaveProjectFile: (
    projectId: string,
    payload: { path: string; language: string; content: string },
  ) => Promise<void>;
}) {
  const [workspaceForm] = Form.useForm();
  const [projectForm] = Form.useForm();
  const [fileForm] = Form.useForm();
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>();

  useEffect(() => {
    if (!selectedWorkspace) return;
    onLoadProjects(selectedWorkspace).then(setProjects);
  }, [selectedWorkspace, onLoadProjects]);

  const activeWorkspace =
    workspaces.find((item) => item.id === selectedWorkspace) ?? workspaces[0];

  useEffect(() => {
    if (!selectedWorkspace && workspaces[0])
      setSelectedWorkspace(workspaces[0].id);
  }, [workspaces, selectedWorkspace]);

  return (
    <Drawer title="工作区与项目资产" width={760} open={open} onClose={onClose}>
      <div className="workspace-grid">
        <Card title="工作区">
          <Form
            form={workspaceForm}
            layout="vertical"
            initialValues={{
              type: "vertical",
              tags: "全链路开发",
              template_id: "fullstack-delivery",
            }}
            onFinish={async (values) => {
              await onCreateWorkspace({
                name: values.name,
                description: values.description ?? "",
                type: values.type,
                tags: String(values.tags ?? "")
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean),
                config: { template_id: values.template_id },
              });
              workspaceForm.resetFields();
            }}
          >
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input placeholder="业务增长工作区" />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <Input />
            </Form.Item>
            <Space>
              <Form.Item name="type" label="类型">
                <Select
                  style={{ width: 150 }}
                  options={[
                    { label: "垂直类", value: "vertical" },
                    { label: "跨类", value: "cross" },
                    { label: "自定义", value: "custom" },
                  ]}
                />
              </Form.Item>
              <Form.Item name="template_id" label="模板">
                <Select
                  style={{ width: 180 }}
                  options={[
                    { label: "全链路开发", value: "fullstack-delivery" },
                    { label: "数据分析", value: "data-analysis" },
                    { label: "自定义实验", value: "custom-lab" },
                  ]}
                />
              </Form.Item>
            </Space>
            <Form.Item name="tags" label="标签">
              <Input placeholder="逗号分隔" />
            </Form.Item>
            <Button type="primary" htmlType="submit">
              创建工作区
            </Button>
          </Form>
        </Card>
        <Card title="资源概览">
          <List
            dataSource={workspaces}
            renderItem={(workspace) => (
              <List.Item
                className={
                  workspace.id === activeWorkspace?.id ? "workspace-active" : ""
                }
                onClick={() => setSelectedWorkspace(workspace.id)}
              >
                <List.Item.Meta
                  avatar={
                    <Avatar style={{ background: "#1677ff" }}>
                      {workspace.name.slice(0, 1)}
                    </Avatar>
                  }
                  title={
                    <Space>
                      <Text strong>{workspace.name}</Text>
                      <Tag>{workspace.type}</Tag>
                      <Tag>{workspace.status}</Tag>
                    </Space>
                  }
                  description={`${workspace.member_count} 成员 · ${workspace.project_count} 项目 · ${workspace.tags.join("/")}`}
                />
              </List.Item>
            )}
          />
        </Card>
      </div>
      <Divider />
      <Flex justify="space-between" align="center">
        <Title level={4}>{activeWorkspace?.name ?? "项目资产"}</Title>
        <Text type="secondary">
          工作区隔离项目、知识库、Agent 编排和快捷指令
        </Text>
      </Flex>
      <div className="workspace-grid">
        <Card title="创建项目">
          <Form
            form={projectForm}
            layout="vertical"
            initialValues={{ type: "code_project" }}
            onFinish={async (values) => {
              if (!activeWorkspace) return;
              const project = await onCreateProject(activeWorkspace.id, values);
              setProjects((current) => [project, ...current]);
              setSelectedProject(project.id);
              projectForm.resetFields();
            }}
          >
            <Form.Item
              name="name"
              label="项目名称"
              rules={[{ required: true }]}
            >
              <Input placeholder="agenthub-preview" />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <Input />
            </Form.Item>
            <Form.Item name="type" label="项目类型">
              <Select
                options={[
                  { label: "代码工程", value: "code_project" },
                  { label: "业务文档", value: "document" },
                  { label: "交互页面", value: "web_app" },
                ]}
              />
            </Form.Item>
            <Button htmlType="submit">创建项目</Button>
          </Form>
        </Card>
        <Card title="项目文件快照">
          <Select
            className="full-width"
            placeholder="选择项目"
            value={selectedProject}
            onChange={setSelectedProject}
            options={projects.map((project) => ({
              label: `${project.name} · v${project.current_version}`,
              value: project.id,
            }))}
          />
          <Form
            className="mt-8"
            form={fileForm}
            layout="vertical"
            initialValues={{
              path: "src/main.ts",
              language: "typescript",
              content: "export const demo = true;",
            }}
            onFinish={async (values) => {
              if (!selectedProject) return;
              await onSaveProjectFile(selectedProject, values);
              fileForm.resetFields();
            }}
          >
            <Form.Item name="path" label="路径" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="language" label="语言">
              <Input />
            </Form.Item>
            <Form.Item name="content" label="内容">
              <TextArea rows={4} />
            </Form.Item>
            <Button disabled={!selectedProject} htmlType="submit">
              保存文件版本
            </Button>
          </Form>
        </Card>
      </div>
    </Drawer>
  );
}

function PlatformControlDrawer({
  open,
  workspaces,
  activeConversation,
  onClose,
  onCreateWorkspace,
  onCreateProject,
  onLoadProjects,
  onSaveProjectFile,
}: {
  open: boolean;
  workspaces: Workspace[];
  activeConversation?: Conversation;
  onClose: () => void;
  onCreateWorkspace: (payload: {
    name: string;
    description: string;
    type: string;
    tags: string[];
    config?: Record<string, unknown>;
  }) => Promise<void>;
  onCreateProject: (
    workspaceId: string,
    payload: { name: string; description: string; type: string },
  ) => Promise<Project>;
  onLoadProjects: (workspaceId: string) => Promise<Project[]>;
  onSaveProjectFile: (
    projectId: string,
    payload: { path: string; language: string; content: string },
  ) => Promise<void>;
}) {
  const [workspaceForm] = Form.useForm();
  const [projectForm] = Form.useForm();
  const [fileForm] = Form.useForm();
  const [providerForm] = Form.useForm();
  const [modelForm] = Form.useForm();
  const [mcpForm] = Form.useForm();
  const [mcpImportForm] = Form.useForm();
  const [skillForm] = Form.useForm();
  const [skillImportForm] = Form.useForm();
  const [toolForm] = Form.useForm();
  const [toolGenerateForm] = Form.useForm();
  const [sandboxForm] = Form.useForm();
  const [commandForm] = Form.useForm();
  const [remoteForm] = Form.useForm();
  const [selectedWorkspace, setSelectedWorkspace] = useState<string>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>();
  const [modelProviders, setModelProviders] = useState<ModelProvider[]>([]);
  const [modelConfigs, setModelConfigs] = useState<ModelConfig[]>([]);
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [mcpInvocations, setMcpInvocations] = useState<McpInvocation[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [tools, setTools] = useState<ToolDefinition[]>([]);
  const [sandboxes, setSandboxes] = useState<SandboxSession[]>([]);
  const [selectedSandbox, setSelectedSandbox] = useState<string>();
  const [remoteConnections, setRemoteConnections] = useState<
    RemoteConnection[]
  >([]);
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [securityRoles, setSecurityRoles] = useState<SecurityRole[]>([]);
  const [securityUsers, setSecurityUsers] = useState<SecurityUser[]>([]);
  const [auditStats, setAuditStats] = useState<{
    total: number;
    high_risk: number;
    by_action: Record<string, number>;
  }>();
  const [modelTestResult, setModelTestResult] = useState("");
  const [skillTestResult, setSkillTestResult] = useState("");
  const [skillSearch, setSkillSearch] = useState("");
  const [toolInvokeResult, setToolInvokeResult] = useState("");
  const [sandboxResult, setSandboxResult] = useState<SandboxCommandResult>();
  const [mcpInvocationResult, setMcpInvocationResult] = useState("");
  const [routingMode, setRoutingMode] = useState("auto");
  const [workflowStatus, setWorkflowStatus] = useState("ready");
  const [conversationWorkflow, setConversationWorkflow] =
    useState<ConversationWorkflow>();
  const [workflowJson, setWorkflowJson] = useState("");
  const [draggingNodeId, setDraggingNodeId] = useState<string>();
  const [workflowRuns, setWorkflowRuns] = useState<WorkflowRun[]>([]);
  const { message } = AntApp.useApp();

  const activeWorkspace =
    workspaces.find((item) => item.id === selectedWorkspace) ?? workspaces[0];
  const filteredSkills = useMemo(() => {
    const keyword = skillSearch.trim().toLowerCase();
    if (!keyword) return skills;
    return skills.filter((skill) =>
      [
        skill.name,
        skill.description,
        skill.category,
        skill.scope,
        skill.source,
        ...(skill.tools ?? []),
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(keyword)),
    );
  }, [skills, skillSearch]);

  const parseList = (value?: string) =>
    String(value ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

  const loadProjects = async () => {
    if (!activeWorkspace) return;
    setProjects(await onLoadProjects(activeWorkspace.id));
  };

  const loadPlatformResources = async () => {
    const [
      providers,
      configs,
      servers,
      nextSkills,
      nextTools,
      sessions,
      remotes,
      invocations,
      logs,
      roles,
      users,
      stats,
    ] = await Promise.all([
      api.modelProviders(),
      api.modelConfigs(),
      api.mcpServers(activeWorkspace?.id),
      api.skills(activeWorkspace?.id),
      api.tools(activeWorkspace?.id),
      api.sandboxes(),
      api.remoteConnections(),
      api.mcpInvocations().catch(() => []),
      api.auditLogs().catch(() => []),
      api.securityRoles().catch(() => []),
      api.securityUsers().catch(() => []),
      api.auditStats().catch(() => undefined),
    ]);
    setModelProviders(providers);
    setModelConfigs(configs);
    setMcpServers(servers);
    setMcpInvocations(invocations);
    setSkills(nextSkills);
    setTools(nextTools);
    setSandboxes(sessions);
    setRemoteConnections(remotes);
    setAuditLogs(logs);
    setSecurityRoles(roles);
    setSecurityUsers(users);
    setAuditStats(stats);
    if (!selectedSandbox && sessions[0]) setSelectedSandbox(sessions[0].id);
  };

  const loadConversationWorkflow = async () => {
    if (!activeConversation?.id) {
      setConversationWorkflow(undefined);
      setWorkflowJson("");
      return;
    }
    const workflow = await api.conversationWorkflow(activeConversation.id);
    const runs = await api.workflowRuns(activeConversation.id).catch(() => []);
    setConversationWorkflow(workflow);
    setWorkflowJson(JSON.stringify(workflow, null, 2));
    setWorkflowRuns(runs);
  };

  useEffect(() => {
    if (!selectedWorkspace && workspaces[0])
      setSelectedWorkspace(workspaces[0].id);
  }, [workspaces, selectedWorkspace]);

  useEffect(() => {
    if (open) {
      loadProjects();
      loadPlatformResources();
      loadConversationWorkflow();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeWorkspace?.id, activeConversation?.id]);

  const workflowIcon = (role?: string) => {
    if (role === "input") return <MessageOutlined />;
    if (role === "master") return <BranchesOutlined />;
    if (role === "reviewer") return <CheckCircleOutlined />;
    if (role === "artifact") return <RocketOutlined />;
    return <RobotOutlined />;
  };
  const workflowNodes = conversationWorkflow?.nodes ?? [];
  const workflowEdges = conversationWorkflow?.edges ?? [];

  const setWorkflowDraft = (next: ConversationWorkflow) => {
    setConversationWorkflow(next);
    setWorkflowJson(JSON.stringify(next, null, 2));
  };

  const reorderWorkflowNode = (sourceId: string, targetId: string) => {
    if (!conversationWorkflow || sourceId === targetId) return;
    const nodes = [...conversationWorkflow.nodes];
    const from = nodes.findIndex((node) => node.id === sourceId);
    const to = nodes.findIndex((node) => node.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = nodes.splice(from, 1);
    nodes.splice(to, 0, moved);
    const edges = nodes
      .slice(1)
      .map((node, index) => [nodes[index].id, node.id]);
    setWorkflowDraft({ ...conversationWorkflow, nodes, edges });
  };

  return (
    <Drawer
      title="工作区与平台控制面"
      width={1040}
      open={open}
      onClose={onClose}
    >
      <Flex justify="space-between" align="center" className="drawer-toolbar">
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder="选择工作区"
            value={activeWorkspace?.id}
            onChange={setSelectedWorkspace}
            options={workspaces.map((workspace) => ({
              label: workspace.name,
              value: workspace.id,
            }))}
          />
          {activeWorkspace && (
            <>
              <Tag color="blue">{activeWorkspace.type}</Tag>
              <Tag>{activeWorkspace.status}</Tag>
              <Tag>{activeWorkspace.member_count} 成员</Tag>
              <Tag>{activeWorkspace.project_count} 项目</Tag>
            </>
          )}
        </Space>
        <Button icon={<ReloadOutlined />} onClick={loadPlatformResources}>
          刷新
        </Button>
      </Flex>
      <Tabs
        items={[
          {
            key: "assets",
            label: "资产",
            children: (
              <>
                <div className="workspace-grid">
                  <Card title="创建工作区">
                    <Form
                      form={workspaceForm}
                      layout="vertical"
                      initialValues={{
                        type: "vertical",
                        tags: "fullstack,demo",
                        template_id: "fullstack-delivery",
                      }}
                      onFinish={async (values) => {
                        await onCreateWorkspace({
                          name: values.name,
                          description: values.description ?? "",
                          type: values.type,
                          tags: parseList(values.tags),
                          config: { template_id: values.template_id },
                        });
                        workspaceForm.resetFields();
                      }}
                    >
                      <Form.Item
                        name="name"
                        label="名称"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="业务增长工作区" />
                      </Form.Item>
                      <Form.Item name="description" label="描述">
                        <Input />
                      </Form.Item>
                      <Space align="start">
                        <Form.Item name="type" label="类型">
                          <Select
                            style={{ width: 150 }}
                            options={[
                              { label: "垂直业务", value: "vertical" },
                              { label: "跨团队", value: "cross" },
                              { label: "自定义", value: "custom" },
                            ]}
                          />
                        </Form.Item>
                        <Form.Item name="template_id" label="模板">
                          <Select
                            style={{ width: 180 }}
                            options={[
                              {
                                label: "全链路开发",
                                value: "fullstack-delivery",
                              },
                              { label: "数据分析", value: "data-analysis" },
                              { label: "自定义实验", value: "custom-lab" },
                            ]}
                          />
                        </Form.Item>
                      </Space>
                      <Form.Item name="tags" label="标签">
                        <Input placeholder="逗号分隔" />
                      </Form.Item>
                      <Button type="primary" htmlType="submit">
                        创建工作区
                      </Button>
                    </Form>
                  </Card>
                  <Card title="资源概览">
                    <List
                      dataSource={workspaces}
                      renderItem={(workspace) => (
                        <List.Item
                          className={
                            workspace.id === activeWorkspace?.id
                              ? "workspace-active"
                              : ""
                          }
                          onClick={() => setSelectedWorkspace(workspace.id)}
                        >
                          <List.Item.Meta
                            avatar={
                              <Avatar style={{ background: "#1677ff" }}>
                                {workspace.name.slice(0, 1)}
                              </Avatar>
                            }
                            title={
                              <Space>
                                <Text strong>{workspace.name}</Text>
                                <Tag>{workspace.type}</Tag>
                                <Tag>{workspace.status}</Tag>
                              </Space>
                            }
                            description={`${workspace.member_count} 成员 · ${workspace.project_count} 项目 · ${workspace.tags.join("/")}`}
                          />
                        </List.Item>
                      )}
                    />
                  </Card>
                </div>
                <Divider />
                <div className="workspace-grid">
                  <Card title="创建项目">
                    <Form
                      form={projectForm}
                      layout="vertical"
                      initialValues={{ type: "code_project" }}
                      onFinish={async (values) => {
                        if (!activeWorkspace) return;
                        const project = await onCreateProject(
                          activeWorkspace.id,
                          values,
                        );
                        setProjects((current) => [project, ...current]);
                        setSelectedProject(project.id);
                        projectForm.resetFields();
                      }}
                    >
                      <Form.Item
                        name="name"
                        label="项目名称"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="agenthub-preview" />
                      </Form.Item>
                      <Form.Item name="description" label="描述">
                        <Input />
                      </Form.Item>
                      <Form.Item name="type" label="项目类型">
                        <Select
                          options={[
                            { label: "代码工程", value: "code_project" },
                            { label: "业务文档", value: "document" },
                            { label: "交互页面", value: "web_app" },
                          ]}
                        />
                      </Form.Item>
                      <Button htmlType="submit" disabled={!activeWorkspace}>
                        创建项目
                      </Button>
                    </Form>
                  </Card>
                  <Card title="项目文件快照">
                    <Select
                      className="full-width"
                      placeholder="选择项目"
                      value={selectedProject}
                      onChange={setSelectedProject}
                      options={projects.map((project) => ({
                        label: `${project.name} · v${project.current_version}`,
                        value: project.id,
                      }))}
                    />
                    <Form
                      className="mt-8"
                      form={fileForm}
                      layout="vertical"
                      initialValues={{
                        path: "src/main.ts",
                        language: "typescript",
                        content: "export const demo = true;",
                      }}
                      onFinish={async (values) => {
                        if (!selectedProject) return;
                        await onSaveProjectFile(selectedProject, values);
                        fileForm.resetFields();
                      }}
                    >
                      <Form.Item
                        name="path"
                        label="路径"
                        rules={[{ required: true }]}
                      >
                        <Input />
                      </Form.Item>
                      <Form.Item name="language" label="语言">
                        <Input />
                      </Form.Item>
                      <Form.Item name="content" label="内容">
                        <TextArea rows={4} />
                      </Form.Item>
                      <Button disabled={!selectedProject} htmlType="submit">
                        保存文件版本
                      </Button>
                    </Form>
                  </Card>
                </div>
              </>
            ),
          },
          {
            key: "workflow",
            label: "工作流画布",
            children: (
              <div className="workflow-board">
                <div className="workflow-canvas">
                  {workflowNodes.length ? (
                    workflowNodes.map((node, index) => (
                      <div
                        key={node.id}
                        className={`workflow-node workflow-node-${node.status}`}
                        draggable
                        onDragStart={() => setDraggingNodeId(node.id)}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={() => {
                          if (draggingNodeId)
                            reorderWorkflowNode(draggingNodeId, node.id);
                          setDraggingNodeId(undefined);
                        }}
                      >
                        <div className="workflow-node-icon">
                          {workflowIcon(node.role)}
                        </div>
                        <div className="workflow-node-body">
                          <Text strong>{node.title}</Text>
                          <Text type="secondary">{node.meta}</Text>
                        </div>
                        {index < workflowNodes.length - 1 && (
                          <div className="workflow-arrow">→</div>
                        )}
                      </div>
                    ))
                  ) : (
                    <Empty description="选择一个会话后，可按群聊 Agent 自动生成工作流" />
                  )}
                </div>
                <div className="workflow-side">
                  <Card title="会话工作流">
                    <Space direction="vertical" className="full-width">
                      <Text type="secondary">
                        {activeConversation
                          ? activeConversation.title
                          : "暂无选中会话"}
                      </Text>
                      <Space wrap>
                        <Button
                          icon={<RobotOutlined />}
                          disabled={!activeConversation}
                          onClick={async () => {
                            if (!activeConversation) return;
                            const workflow =
                              await api.generateConversationWorkflow(
                                activeConversation.id,
                              );
                            setConversationWorkflow(workflow);
                            setWorkflowJson(JSON.stringify(workflow, null, 2));
                            message.success("AI 已按当前群聊 Agent 生成工作流");
                          }}
                        >
                          AI 生成
                        </Button>
                        <Button
                          icon={<CheckCircleOutlined />}
                          disabled={!activeConversation || !workflowJson.trim()}
                          onClick={async () => {
                            if (!activeConversation) return;
                            let workflow: ConversationWorkflow;
                            try {
                              workflow = JSON.parse(
                                workflowJson,
                              ) as ConversationWorkflow;
                            } catch {
                              message.error("工作流 JSON 格式不正确");
                              return;
                            }
                            const saved = await api.saveConversationWorkflow(
                              activeConversation.id,
                              workflow,
                            );
                            setConversationWorkflow(saved);
                            setWorkflowJson(JSON.stringify(saved, null, 2));
                            message.success("工作流已保存");
                          }}
                        >
                          保存
                        </Button>
                      </Space>
                      <Button
                        icon={<PlusOutlined />}
                        disabled={!conversationWorkflow}
                        onClick={() => {
                          if (!conversationWorkflow) return;
                          const id = `node-${Date.now().toString(36)}`;
                          const nodes = [
                            ...conversationWorkflow.nodes,
                            {
                              id,
                              title: "New node",
                              role: "worker",
                              status: "ready",
                              meta: "Manual step",
                            },
                          ];
                          const edges = nodes
                            .slice(1)
                            .map((node, index) => [nodes[index].id, node.id]);
                          setWorkflowDraft({
                            ...conversationWorkflow,
                            nodes,
                            edges,
                          });
                        }}
                      >
                        Add node
                      </Button>
                      <Button
                        icon={<BranchesOutlined />}
                        disabled={!activeConversation || !conversationWorkflow}
                        onClick={async () => {
                          if (!activeConversation || !conversationWorkflow)
                            return;
                          const run = await api.startWorkflowRun(
                            activeConversation.id,
                            conversationWorkflow,
                          );
                          setWorkflowRuns((current) => [run, ...current]);
                          message.success("Workflow run started");
                        }}
                      >
                        Run
                      </Button>
                      <TextArea
                        rows={10}
                        value={workflowJson}
                        onChange={(event) =>
                          setWorkflowJson(event.target.value)
                        }
                        placeholder="工作流 JSON：nodes / edges / settings"
                      />
                    </Space>
                  </Card>
                  <Card title="调度参数" className="mt-8">
                    <Space direction="vertical" className="full-width">
                      <Segmented
                        block
                        value={routingMode}
                        onChange={(value) => setRoutingMode(String(value))}
                        options={[
                          { label: "自动", value: "auto" },
                          { label: "人工确认", value: "human" },
                          { label: "成本优先", value: "cost" },
                        ]}
                      />
                      <Select
                        defaultValue="review-required"
                        options={[
                          {
                            label: "Reviewer 必须通过",
                            value: "review-required",
                          },
                          { label: "低风险跳过", value: "risk-based" },
                          { label: "双 Reviewer", value: "dual-review" },
                        ]}
                      />
                      <Select
                        defaultValue="summary-window"
                        options={[
                          { label: "摘要滚动窗口", value: "summary-window" },
                          { label: "全量上下文", value: "full-context" },
                          { label: "知识库优先", value: "kb-first" },
                        ]}
                      />
                      <Button
                        type="primary"
                        icon={<BranchesOutlined />}
                        onClick={() => {
                          setWorkflowStatus("running");
                          setConversationWorkflow((current) =>
                            current
                              ? {
                                  ...current,
                                  nodes: current.nodes.map((node) =>
                                    node.role === "master"
                                      ? { ...node, status: "running" }
                                      : node,
                                  ),
                                }
                              : current,
                          );
                          window.setTimeout(() => {
                            setWorkflowStatus("ready");
                            setConversationWorkflow((current) =>
                              current
                                ? {
                                    ...current,
                                    nodes: current.nodes.map((node) =>
                                      node.role === "master"
                                        ? { ...node, status: "ready" }
                                        : node,
                                    ),
                                  }
                                : current,
                            );
                          }, 1200);
                          message.success(`调度演练已触发：${routingMode}`);
                        }}
                      >
                        调度演练
                      </Button>
                    </Space>
                  </Card>
                  <Card title="依赖连线" className="mt-8">
                    <List
                      size="small"
                      dataSource={workflowEdges}
                      renderItem={([from, to]) => (
                        <List.Item>
                          <Tag>{from}</Tag>
                          <span>→</span>
                          <Tag color="blue">{to}</Tag>
                        </List.Item>
                      )}
                    />
                  </Card>
                </div>
              </div>
            ),
          },
          {
            key: "models",
            label: "模型",
            children: (
              <div className="workspace-grid">
                <Card title="OpenAI 兼容供应商">
                  <Form
                    form={providerForm}
                    layout="vertical"
                    initialValues={{
                      provider_type: "openai-compatible",
                      base_url: "https://ark.cn-beijing.volces.com/api/v3",
                      default_model: "doubao-seed-2-0-lite",
                      supports_streaming: true,
                    }}
                    onFinish={async (values) => {
                      const provider = await api.createModelProvider({
                        ...values,
                        supports_streaming: Boolean(values.supports_streaming),
                        supports_embeddings: Boolean(
                          values.supports_embeddings,
                        ),
                      });
                      setModelProviders((current) => [provider, ...current]);
                      providerForm.resetFields(["name", "api_key"]);
                      message.success("模型供应商已创建");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="我的 OpenAI 兼容模型" />
                    </Form.Item>
                    <Form.Item name="provider_type" label="类型">
                      <Select
                        options={[
                          {
                            label: "OpenAI Compatible",
                            value: "openai-compatible",
                          },
                          { label: "火山方舟", value: "ark" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="base_url"
                      label="Base URL"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item name="api_key" label="API Key">
                      <Input.Password placeholder="仅提交到后端保存，前端不回显" />
                    </Form.Item>
                    <Form.Item
                      name="default_model"
                      label="默认模型"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Space>
                      <Form.Item
                        name="supports_streaming"
                        valuePropName="checked"
                      >
                        <Checkbox>流式</Checkbox>
                      </Form.Item>
                      <Form.Item
                        name="supports_embeddings"
                        valuePropName="checked"
                      >
                        <Checkbox>Embedding</Checkbox>
                      </Form.Item>
                    </Space>
                    <Button type="primary" htmlType="submit">
                      保存供应商
                    </Button>
                  </Form>
                </Card>
                <Card title="模型配置与测试">
                  <Form
                    form={modelForm}
                    layout="vertical"
                    initialValues={{
                      purpose: "chat",
                      context_window: 128000,
                      max_output_tokens: 4096,
                      temperature_default: 0.4,
                    }}
                    onFinish={async (values) => {
                      const model = await api.createModelConfig(values);
                      setModelConfigs((current) => [model, ...current]);
                      modelForm.resetFields(["name", "model_id"]);
                      message.success("模型配置已创建");
                    }}
                  >
                    <Form.Item
                      name="provider_id"
                      label="供应商"
                      rules={[{ required: true }]}
                    >
                      <Select
                        options={modelProviders.map((provider) => ({
                          label: provider.name,
                          value: provider.id,
                        }))}
                      />
                    </Form.Item>
                    <Space align="start">
                      <Form.Item
                        name="name"
                        label="名称"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="Reviewer 模型" />
                      </Form.Item>
                      <Form.Item
                        name="model_id"
                        label="模型 ID"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="doubao-seed-1-6" />
                      </Form.Item>
                    </Space>
                    <Space align="start">
                      <Form.Item name="purpose" label="用途">
                        <Select
                          style={{ width: 150 }}
                          options={[
                            { label: "聊天", value: "chat" },
                            { label: "主控", value: "master" },
                            { label: "Worker", value: "worker" },
                            { label: "Reviewer", value: "reviewer" },
                            { label: "摘要", value: "summary" },
                          ]}
                        />
                      </Form.Item>
                      <Form.Item name="temperature_default" label="温度">
                        <Input type="number" step="0.1" />
                      </Form.Item>
                    </Space>
                    <Button htmlType="submit" disabled={!modelProviders.length}>
                      新增模型
                    </Button>
                  </Form>
                  <Divider />
                  <Input.Search
                    placeholder="输入测试提示词"
                    enterButton="测试"
                    onSearch={async (prompt) => {
                      const currentModel = modelConfigs[0];
                      const result = await api.testModel(
                        prompt || "请回复模型已就绪。",
                        currentModel?.id,
                      );
                      setModelTestResult(`${result.model}: ${result.response}`);
                    }}
                  />
                  {modelTestResult && (
                    <div className="result-box">{modelTestResult}</div>
                  )}
                  <List
                    size="small"
                    dataSource={modelConfigs}
                    renderItem={(model) => (
                      <List.Item>
                        <List.Item.Meta
                          avatar={<Avatar icon={<ApiOutlined />} />}
                          title={
                            <Space>
                              <Text strong>{model.name}</Text>
                              <Tag>{model.purpose}</Tag>
                              <Tag>{model.status}</Tag>
                            </Space>
                          }
                          description={`${model.provider_name ?? model.provider_id} · ${model.model_id} · ${model.context_window} tokens`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
          {
            key: "mcp",
            label: "MCP",
            children: (
              <div className="workspace-grid">
                <Card title="注册 MCP 服务">
                  <Form
                    form={mcpForm}
                    layout="vertical"
                    initialValues={{
                      transport: "stdio",
                      command: "agenthub-mcp-sandbox",
                      enabled: true,
                      timeout_ms: 30000,
                      retry: 1,
                    }}
                    onFinish={async (values) => {
                      const server = await api.createMcpServer({
                        workspace_id: activeWorkspace?.id,
                        ...values,
                        args: parseList(values.args),
                        tool_filter: parseList(values.tool_filter),
                        enabled: Boolean(values.enabled),
                      });
                      setMcpServers((current) => [server, ...current]);
                      mcpForm.resetFields([
                        "name",
                        "url",
                        "args",
                        "tool_filter",
                      ]);
                      message.success("MCP 服务已注册");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="文件系统 MCP" />
                    </Form.Item>
                    <Form.Item name="transport" label="传输">
                      <Select
                        options={[
                          { label: "stdio", value: "stdio" },
                          { label: "SSE", value: "sse" },
                          { label: "HTTP Stream", value: "httpStream" },
                          { label: "WebSocket", value: "ws" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item name="command" label="命令">
                      <Input placeholder="npx -y @modelcontextprotocol/server-filesystem" />
                    </Form.Item>
                    <Form.Item name="url" label="URL">
                      <Input placeholder="https://mcp.example.com/sse" />
                    </Form.Item>
                    <Form.Item name="args" label="参数">
                      <Input placeholder="--root, E:/字节跳动/agenthub" />
                    </Form.Item>
                    <Form.Item name="tool_filter" label="工具白名单">
                      <Input placeholder="file.*, browser.*, sandbox.*" />
                    </Form.Item>
                    <Space>
                      <Form.Item name="enabled" valuePropName="checked">
                        <Checkbox>启用</Checkbox>
                      </Form.Item>
                      <Form.Item name="timeout_ms" label="超时">
                        <Input type="number" />
                      </Form.Item>
                    </Space>
                    <Button
                      type="primary"
                      htmlType="submit"
                      disabled={!activeWorkspace}
                    >
                      注册服务
                    </Button>
                  </Form>
                </Card>
                <Card title="服务与工具">
                  <List
                    dataSource={mcpServers}
                    locale={{ emptyText: "暂无 MCP 服务" }}
                    renderItem={(server) => (
                      <List.Item
                        actions={[
                          <Button
                            key="probe"
                            size="small"
                            icon={<ToolOutlined />}
                            onClick={async () => {
                              const updated = await api.probeMcpServer(
                                server.id,
                              );
                              setMcpServers((current) =>
                                current.map((item) =>
                                  item.id === server.id ? updated : item,
                                ),
                              );
                            }}
                          >
                            探测
                          </Button>,
                          <Button
                            key="invoke"
                            size="small"
                            disabled={
                              !(
                                server.tools?.[0]?.name ||
                                server.tool_filter?.[0]
                              )
                            }
                            onClick={async () => {
                              const toolName =
                                server.tools?.[0]?.name ||
                                server.tool_filter?.[0];
                              if (!toolName) return;
                              const result = await api.invokeMcpTool(
                                server.id,
                                toolName,
                                { input: "ping" },
                                activeConversation?.id,
                              );
                              setMcpInvocations((current) => [
                                result,
                                ...current,
                              ]);
                              setMcpInvocationResult(
                                JSON.stringify(
                                  result.result || result.error_message,
                                  null,
                                  2,
                                ),
                              );
                            }}
                          >
                            Invoke
                          </Button>,
                          <Button
                            key="delete"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => {
                              Modal.confirm({
                                title: `删除 MCP 服务：${server.name}`,
                                content:
                                  "删除后该服务、关联工具调用入口将从当前目录移除。",
                                okText: "删除",
                                okButtonProps: { danger: true },
                                onOk: async () => {
                                  await api.deleteMcpServer(server.id);
                                  setMcpServers((current) =>
                                    current.filter(
                                      (item) => item.id !== server.id,
                                    ),
                                  );
                                  message.success("MCP 服务已删除");
                                },
                              });
                            }}
                          />,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={
                            <Badge
                              color={
                                server.health_status === "online"
                                  ? "green"
                                  : "orange"
                              }
                            >
                              <Avatar icon={<ToolOutlined />} />
                            </Badge>
                          }
                          title={
                            <Space>
                              <Text strong>{server.name}</Text>
                              <Tag>{server.transport}</Tag>
                              <Tag>{server.health_status}</Tag>
                            </Space>
                          }
                          description={
                            <Space wrap>
                              {(server.tools ?? []).map((tool) => (
                                <Tag
                                  key={tool.name}
                                  color={
                                    tool.enabled === false ? "default" : "blue"
                                  }
                                >
                                  {tool.name}
                                </Tag>
                              ))}
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                </Card>
                <Card title="导入 MCP" data-testid="mcp-import-card">
                  <Form
                    form={mcpImportForm}
                    layout="vertical"
                    initialValues={{ source_type: "manifest_url" }}
                    onFinish={async (values) => {
                      const server = await api.importMcpServer({
                        workspace_id: activeWorkspace?.id,
                        source_type: values.source_type,
                        source: values.source,
                      });
                      setMcpServers((current) => [server, ...current]);
                      mcpImportForm.resetFields(["source"]);
                      message.success("MCP 已导入");
                    }}
                  >
                    <Form.Item name="source_type" label="导入类型">
                      <Select
                        options={[
                          { label: "Manifest URL", value: "manifest_url" },
                          { label: "JSON 配置", value: "json" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="source"
                      label="URL / JSON"
                      rules={[{ required: true }]}
                    >
                      <TextArea
                        rows={5}
                        placeholder='https://example.com/mcp.json 或 {"name":"filesystem","transport":"stdio"}'
                      />
                    </Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      icon={<CloudUploadOutlined />}
                      disabled={!activeWorkspace}
                    >
                      导入 MCP
                    </Button>
                  </Form>
                </Card>
              </div>
            ),
          },
          {
            key: "tools",
            label: "工具",
            children: (
              <div className="workspace-grid">
                <Card title="自定义工具">
                  <Form
                    form={toolForm}
                    layout="vertical"
                    initialValues={{
                      category: "custom",
                      type: "custom_python",
                      permissions: "tool:invoke",
                      code: "text = str(arguments.get('input') or '')\nresult = {'echo': text, 'length': len(text)}",
                    }}
                    onFinish={async (values) => {
                      const tool = await api.createTool({
                        workspace_id: activeWorkspace?.id,
                        name: values.name,
                        display_name: values.display_name,
                        description: values.description ?? "",
                        category: values.category,
                        type: values.type,
                        permissions: parseList(values.permissions),
                        implementation: {
                          language: "python",
                          code: values.code,
                        },
                        runtime: {
                          mode: "restricted_python",
                          workspace: "var/ai-tools",
                        },
                        tags: parseList(values.tags),
                      });
                      setTools((current) => [tool, ...current]);
                      toolForm.resetFields([
                        "name",
                        "display_name",
                        "description",
                      ]);
                      message.success("工具已创建");
                    }}
                  >
                    <Space align="start">
                      <Form.Item
                        name="name"
                        label="工具名"
                        rules={[{ required: true }]}
                      >
                        <Input placeholder="custom_release_notes" />
                      </Form.Item>
                      <Form.Item name="display_name" label="显示名">
                        <Input placeholder="发布说明生成器" />
                      </Form.Item>
                    </Space>
                    <Form.Item name="description" label="描述">
                      <Input placeholder="说明这个工具适合什么任务" />
                    </Form.Item>
                    <Space align="start">
                      <Form.Item name="category" label="分类">
                        <Input style={{ width: 150 }} />
                      </Form.Item>
                      <Form.Item name="type" label="运行时">
                        <Select
                          style={{ width: 170 }}
                          options={[
                            { label: "受限 Python", value: "custom_python" },
                          ]}
                        />
                      </Form.Item>
                    </Space>
                    <Form.Item name="permissions" label="权限">
                      <Input placeholder="逗号分隔，如 file:read,artifact:create" />
                    </Form.Item>
                    <Form.Item name="code" label="工具代码">
                      <TextArea rows={5} />
                    </Form.Item>
                    <Form.Item name="tags" label="标签">
                      <Input placeholder="逗号分隔" />
                    </Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      disabled={!activeWorkspace}
                    >
                      保存工具
                    </Button>
                  </Form>
                </Card>
                <Card title="AI 构建工具">
                  <Form
                    form={toolGenerateForm}
                    layout="vertical"
                    initialValues={{
                      category: "custom",
                      allowed_permissions: "tool:invoke",
                    }}
                    onFinish={async (values) => {
                      const tool = await api.generateTool({
                        workspace_id: activeWorkspace?.id,
                        name: values.name,
                        intent: values.intent,
                        requirements: values.requirements,
                        category: values.category,
                        allowed_permissions: parseList(
                          values.allowed_permissions,
                        ),
                        tags: parseList(values.tags),
                      });
                      setTools((current) => [tool, ...current]);
                      toolGenerateForm.resetFields([
                        "name",
                        "intent",
                        "requirements",
                      ]);
                      message.success("AI 已构建工具并写入后端工具工作区");
                    }}
                  >
                    <Form.Item name="name" label="工具名">
                      <Input placeholder="留空由 AI 命名" />
                    </Form.Item>
                    <Form.Item
                      name="intent"
                      label="工具目标"
                      rules={[{ required: true }]}
                    >
                      <TextArea
                        rows={3}
                        placeholder="例如：把输入的需求整理成验收清单 JSON"
                      />
                    </Form.Item>
                    <Form.Item name="requirements" label="实现约束">
                      <TextArea
                        rows={3}
                        placeholder="输入输出格式、权限边界、异常处理要求"
                      />
                    </Form.Item>
                    <Space align="start">
                      <Form.Item name="category" label="分类">
                        <Input style={{ width: 150 }} />
                      </Form.Item>
                      <Form.Item name="allowed_permissions" label="授权权限">
                        <Input style={{ width: 220 }} />
                      </Form.Item>
                    </Space>
                    <Form.Item name="tags" label="标签">
                      <Input placeholder="ai-generated,workflow" />
                    </Form.Item>
                    <Button
                      icon={<RobotOutlined />}
                      type="primary"
                      htmlType="submit"
                      disabled={!activeWorkspace}
                    >
                      AI 创建工具
                    </Button>
                  </Form>
                </Card>
                <Card title="工具目录">
                  {toolInvokeResult && (
                    <div className="result-box">{toolInvokeResult}</div>
                  )}
                  <List
                    dataSource={tools}
                    locale={{ emptyText: "暂无工具" }}
                    renderItem={(tool) => (
                      <List.Item
                        actions={[
                          <Button
                            key="invoke"
                            size="small"
                            onClick={async () => {
                              if (
                                tool.name.startsWith("artifact.create") &&
                                !activeConversation?.id
                              ) {
                                message.warning("先选择一个会话再测试产物工具");
                                return;
                              }
                              const args =
                                tool.name === "db.inspect"
                                  ? {}
                                  : tool.name.startsWith("artifact.create")
                                    ? {
                                        conversation_id: activeConversation?.id,
                                        title: "工具调用产物",
                                        body: "这是由 AgentHub 工具层生成的产物。",
                                      }
                                    : { input: "ping" };
                              const result = await api.invokeTool(
                                tool.name,
                                args,
                                activeWorkspace?.id,
                              );
                              setToolInvokeResult(
                                JSON.stringify(result.result, null, 2),
                              );
                            }}
                          >
                            测试
                          </Button>,
                          !tool.is_builtin && (
                            <Button
                              key="delete"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={() => {
                                Modal.confirm({
                                  title: `删除工具：${tool.display_name ?? tool.name}`,
                                  content:
                                    "删除后该工具不会再出现在工具目录，也不能被 Agent 授权使用。",
                                  okText: "删除",
                                  okButtonProps: { danger: true },
                                  onOk: async () => {
                                    await api.deleteTool(tool.id);
                                    setTools((current) =>
                                      current.filter(
                                        (item) => item.id !== tool.id,
                                      ),
                                    );
                                    message.success("工具已删除");
                                  },
                                });
                              }}
                            />
                          ),
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<Avatar icon={<ToolOutlined />} />}
                          title={
                            <Space wrap>
                              <Text strong>
                                {tool.display_name ?? tool.name}
                              </Text>
                              <Tag>{tool.category}</Tag>
                              <Tag color={tool.is_builtin ? "blue" : "purple"}>
                                {tool.is_builtin ? "内置" : "自定义"}
                              </Tag>
                              <Tag>{tool.status}</Tag>
                            </Space>
                          }
                          description={
                            <Space direction="vertical" size={4}>
                              <Text type="secondary">
                                {tool.name} · {tool.description}
                              </Text>
                              <Space size={[4, 4]} wrap>
                                {tool.permissions
                                  .slice(0, 6)
                                  .map((permission) => (
                                    <Tag key={permission}>{permission}</Tag>
                                  ))}
                              </Space>
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
          {
            key: "skills",
            label: "Skills",
            children: (
              <div className="workspace-grid">
                <Card title="创建 Skill">
                  <Form
                    form={skillForm}
                    layout="vertical"
                    initialValues={{
                      scope: "workspace",
                      category: "workflow",
                      tools: "file.read,browser.open",
                    }}
                    onFinish={async (values) => {
                      const skill = await api.createSkill({
                        workspace_id: activeWorkspace?.id,
                        name: values.name,
                        description: values.description ?? "",
                        category: values.category,
                        scope: values.scope,
                        prompt_template: values.prompt_template,
                        tools: parseList(values.tools),
                        enabled: true,
                      });
                      setSkills((current) => [skill, ...current]);
                      skillForm.resetFields([
                        "name",
                        "description",
                        "prompt_template",
                      ]);
                      message.success("Skill 已创建");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="Skill 名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="前端审查 Skill" />
                    </Form.Item>
                    <Form.Item name="description" label="描述">
                      <Input />
                    </Form.Item>
                    <Space align="start">
                      <Form.Item name="category" label="分类">
                        <Input style={{ width: 160 }} />
                      </Form.Item>
                      <Form.Item name="scope" label="范围">
                        <Select
                          style={{ width: 160 }}
                          options={[
                            { label: "工作区", value: "workspace" },
                            { label: "平台", value: "platform" },
                            { label: "个人", value: "personal" },
                          ]}
                        />
                      </Form.Item>
                    </Space>
                    <Form.Item name="prompt_template" label="Prompt 模板">
                      <TextArea rows={4} />
                    </Form.Item>
                    <Form.Item name="tools" label="工具">
                      <Input placeholder="逗号分隔，如 file.read,browser.open" />
                    </Form.Item>
                    <Space>
                      <Button
                        type="primary"
                        htmlType="submit"
                        disabled={!activeWorkspace}
                      >
                        保存 Skill
                      </Button>
                      <Button
                        icon={<RobotOutlined />}
                        data-testid="ai-generate-skill"
                        disabled={!activeWorkspace}
                        onClick={async () => {
                          const values = skillForm.getFieldsValue();
                          const intent = [
                            values.name,
                            values.description,
                            values.prompt_template,
                          ]
                            .filter(Boolean)
                            .join("\n");
                          if (!intent.trim()) {
                            message.warning("先输入 Skill 名称、描述或目标");
                            return;
                          }
                          const skill = await api.generateSkill({
                            workspace_id: activeWorkspace?.id,
                            name: values.name,
                            intent,
                            requirements: values.prompt_template ?? "",
                            category: values.category || "ai",
                            tags: parseList(values.tools),
                          });
                          setSkills((current) => [skill, ...current]);
                          skillForm.setFieldsValue({
                            name: skill.name,
                            description: skill.description,
                            category: skill.category,
                            prompt_template: skill.prompt_template,
                            tools: skill.tools.join(","),
                          });
                          message.success("AI 已创建 Skill");
                        }}
                      >
                        AI 创建 Skill
                      </Button>
                    </Space>
                  </Form>
                </Card>
                <Card title="Skill 目录">
                  <Flex
                    justify="space-between"
                    align="center"
                    wrap="wrap"
                    gap={8}
                    style={{ marginBottom: 12 }}
                  >
                    <Input.Search
                      allowClear
                      style={{ maxWidth: 340 }}
                      placeholder="搜索 Skill 名称、分类或工具"
                      value={skillSearch}
                      onChange={(event) => setSkillSearch(event.target.value)}
                    />
                    <Space>
                      <Tag>
                        {filteredSkills.length}/{skills.length} Skills
                      </Tag>
                      <Button
                        icon={<ReloadOutlined />}
                        onClick={loadPlatformResources}
                      >
                        刷新
                      </Button>
                    </Space>
                  </Flex>
                  <Form
                    form={skillImportForm}
                    layout="vertical"
                    onFinish={async (values) => {
                      const skill = await api.importMcpAsSkill({
                        workspace_id: activeWorkspace?.id,
                        mcp_server_id: values.mcp_server_id,
                        name: values.name,
                        category: "mcp",
                      });
                      setSkills((current) => [skill, ...current]);
                      skillImportForm.resetFields(["name"]);
                      message.success("已从 MCP 导入 Skill");
                    }}
                  >
                    <Form.Item
                      name="mcp_server_id"
                      label="MCP 服务"
                      rules={[{ required: true }]}
                    >
                      <Select
                        placeholder="选择已注册 MCP"
                        options={mcpServers.map((server) => ({
                          label: `${server.name} · ${server.transport}`,
                          value: server.id,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name="name" label="Skill 名称">
                      <Input placeholder="留空则使用 MCP 名称" />
                    </Form.Item>
                    <Button
                      htmlType="submit"
                      icon={<ToolOutlined />}
                      disabled={!mcpServers.length}
                    >
                      从 MCP 导入 Skill
                    </Button>
                  </Form>
                  <Divider />
                  {skillTestResult && (
                    <div className="result-box">{skillTestResult}</div>
                  )}
                  <List
                    dataSource={filteredSkills}
                    locale={{ emptyText: "暂无 Skills" }}
                    renderItem={(skill) => (
                      <List.Item
                        actions={[
                          <Button
                            key="test"
                            size="small"
                            onClick={async () => {
                              const result = await api.testSkill(
                                skill.id,
                                `请测试 ${skill.name} 是否可用，并用一句话说明。`,
                              );
                              setSkillTestResult(
                                `${result.model}: ${result.response}`,
                              );
                            }}
                          >
                            测试
                          </Button>,
                          (skill.created_by ||
                            skill.workspace_id === activeWorkspace?.id) &&
                            !Boolean(skill.config?.builtin) && (
                              <Button
                                key="delete"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => {
                                  Modal.confirm({
                                    title: `删除 Skill：${skill.name}`,
                                    content:
                                      "删除后将不再出现在当前工作区 Skill 目录，也不能再授权给 Agent 使用。",
                                    okText: "删除",
                                    okButtonProps: { danger: true },
                                    onOk: async () => {
                                      try {
                                        await api.deleteSkill(skill.id);
                                        setSkills((current) =>
                                          current.filter(
                                            (item) => item.id !== skill.id,
                                          ),
                                        );
                                        setSkillTestResult("");
                                        message.success("Skill 已删除");
                                      } catch (error) {
                                        message.error(
                                          error instanceof Error
                                            ? error.message
                                            : "删除失败",
                                        );
                                        throw error;
                                      }
                                    },
                                  });
                                }}
                              >
                                删除
                              </Button>
                            ),
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<Avatar icon={<ToolOutlined />} />}
                          title={
                            <Space>
                              <Text strong>{skill.name}</Text>
                              <Tag>{skill.category}</Tag>
                              <Tag
                                color={skill.workspace_id ? "purple" : "blue"}
                              >
                                {skill.workspace_id ? "工作区" : "全局"}
                              </Tag>
                              {Boolean(skill.config?.builtin) && (
                                <Tag color="geekblue">内置</Tag>
                              )}
                              <Tag
                                color={skill.enabled ? "success" : "default"}
                              >
                                {skill.enabled ? "enabled" : "disabled"}
                              </Tag>
                              {skill.source === "mcp" && (
                                <Tag color="blue">MCP</Tag>
                              )}
                            </Space>
                          }
                          description={
                            <Space direction="vertical" size={4}>
                              <Text type="secondary">
                                {skill.description || "暂无描述"}
                              </Text>
                              <Space size={[4, 4]} wrap>
                                {(skill.tools ?? []).map((tool) => (
                                  <Tag key={tool}>{tool}</Tag>
                                ))}
                              </Space>
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
          {
            key: "security",
            label: "Security",
            children: (
              <div className="workspace-grid">
                <Card title="Audit">
                  <Space className="mb-8" wrap>
                    <Statistic
                      title="Events"
                      value={auditStats?.total ?? auditLogs.length}
                    />
                    <Statistic
                      title="High risk"
                      value={auditStats?.high_risk ?? 0}
                    />
                  </Space>
                  <Table
                    size="small"
                    rowKey="id"
                    dataSource={auditLogs}
                    pagination={{ pageSize: 6 }}
                    columns={[
                      { title: "Action", dataIndex: "action" },
                      {
                        title: "Target",
                        render: (_, row: AuditLog) =>
                          `${row.target_type}:${row.target_id ?? "-"}`,
                      },
                      { title: "Risk", dataIndex: "risk_score" },
                      {
                        title: "Time",
                        dataIndex: "created_at",
                        render: (value?: string) => formatTime(value),
                      },
                    ]}
                  />
                </Card>
                <Card title="Roles and users">
                  <List
                    size="small"
                    dataSource={securityRoles}
                    renderItem={(role) => (
                      <List.Item>
                        <List.Item.Meta
                          title={
                            <Space>
                              <Text strong>{role.code}</Text>
                              <Tag>{role.permissions.length} perms</Tag>
                            </Space>
                          }
                          description={role.description}
                        />
                      </List.Item>
                    )}
                  />
                  <Divider />
                  <List
                    size="small"
                    dataSource={securityUsers}
                    renderItem={(item) => (
                      <List.Item>
                        <List.Item.Meta
                          avatar={
                            <Avatar>{item.display_name.slice(0, 1)}</Avatar>
                          }
                          title={
                            <Space>
                              <Text strong>{item.display_name}</Text>
                              <Tag>{item.role}</Tag>
                            </Space>
                          }
                          description={`${item.email} · ${item.roles.join(", ") || "ROLE_USER"}`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
          {
            key: "sandbox",
            label: "沙箱/远程",
            children: (
              <div className="workspace-grid">
                <Card title="沙箱控制">
                  <Form
                    form={sandboxForm}
                    layout="vertical"
                    initialValues={{ image: "python:3.11-node20" }}
                    onFinish={async (values) => {
                      const sandbox = await api.createSandbox({
                        workspace_id: activeWorkspace?.id,
                        ...values,
                      });
                      setSandboxes((current) => [sandbox, ...current]);
                      setSelectedSandbox(sandbox.id);
                      sandboxForm.resetFields(["name"]);
                      message.success("沙箱已创建");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="前端构建沙箱" />
                    </Form.Item>
                    <Form.Item name="image" label="镜像">
                      <Input />
                    </Form.Item>
                    <Button htmlType="submit" disabled={!activeWorkspace}>
                      创建沙箱
                    </Button>
                  </Form>
                  <Divider />
                  <Select
                    className="full-width"
                    placeholder="选择沙箱"
                    value={selectedSandbox}
                    onChange={setSelectedSandbox}
                    options={sandboxes.map((sandbox) => ({
                      label: `${sandbox.name} · ${sandbox.status}`,
                      value: sandbox.id,
                    }))}
                  />
                  <Form
                    className="mt-8"
                    form={commandForm}
                    layout="vertical"
                    initialValues={{
                      command: "pytest -q",
                      timeout_seconds: 120,
                    }}
                    onFinish={async (values) => {
                      if (!selectedSandbox) return;
                      const result = await api.runSandboxCommand(
                        selectedSandbox,
                        values,
                      );
                      setSandboxResult(result.result);
                      setSandboxes((current) =>
                        current.map((item) =>
                          item.id === selectedSandbox ? result.sandbox : item,
                        ),
                      );
                    }}
                  >
                    <Form.Item
                      name="command"
                      label="命令"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item name="timeout_seconds" label="超时秒数">
                      <Input type="number" />
                    </Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      disabled={!selectedSandbox}
                    >
                      执行
                    </Button>
                  </Form>
                  {sandboxResult && (
                    <div className="terminal-box">
                      <Text>{sandboxResult.command}</Text>
                      <pre>{sandboxResult.stdout || sandboxResult.stderr}</pre>
                    </div>
                  )}
                </Card>
                <Card title="远程连接">
                  <Form
                    form={remoteForm}
                    layout="vertical"
                    initialValues={{
                      connection_type: "browser",
                      endpoint: "http://127.0.0.1:5173",
                      capabilities: "open,screenshot,inspect",
                    }}
                    onFinish={async (values) => {
                      const remote = await api.createRemoteConnection({
                        workspace_id: activeWorkspace?.id,
                        ...values,
                        capabilities: parseList(values.capabilities),
                      });
                      setRemoteConnections((current) => [remote, ...current]);
                      remoteForm.resetFields(["name"]);
                      message.success("远程连接已创建");
                    }}
                  >
                    <Form.Item
                      name="name"
                      label="名称"
                      rules={[{ required: true }]}
                    >
                      <Input placeholder="预览浏览器" />
                    </Form.Item>
                    <Form.Item name="connection_type" label="类型">
                      <Select
                        options={[
                          { label: "Browser", value: "browser" },
                          { label: "SSH", value: "ssh" },
                          { label: "VNC", value: "vnc" },
                          { label: "RDP", value: "rdp" },
                        ]}
                      />
                    </Form.Item>
                    <Form.Item
                      name="endpoint"
                      label="Endpoint"
                      rules={[{ required: true }]}
                    >
                      <Input />
                    </Form.Item>
                    <Form.Item name="capabilities" label="能力">
                      <Input />
                    </Form.Item>
                    <Button htmlType="submit" disabled={!activeWorkspace}>
                      新建连接
                    </Button>
                  </Form>
                  <Divider />
                  <List
                    dataSource={remoteConnections}
                    locale={{ emptyText: "暂无远程连接" }}
                    renderItem={(remote) => (
                      <List.Item
                        actions={[
                          <Button
                            key="connect"
                            size="small"
                            icon={<CloudUploadOutlined />}
                            onClick={async () => {
                              const updated = await api.connectRemote(
                                remote.id,
                              );
                              setRemoteConnections((current) =>
                                current.map((item) =>
                                  item.id === remote.id ? updated : item,
                                ),
                              );
                            }}
                          >
                            连接
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={
                            <Badge
                              status={
                                remote.status === "connected"
                                  ? "success"
                                  : "default"
                              }
                            >
                              <Avatar icon={<CloudUploadOutlined />} />
                            </Badge>
                          }
                          title={
                            <Space>
                              <Text strong>{remote.name}</Text>
                              <Tag>{remote.connection_type}</Tag>
                              <Tag>{remote.status}</Tag>
                            </Space>
                          }
                          description={`${remote.endpoint} · ${remote.capabilities.join("/")}`}
                        />
                      </List.Item>
                    )}
                  />
                </Card>
              </div>
            ),
          },
        ].filter((item) => !["workflow", "models"].includes(String(item.key)))}
      />
    </Drawer>
  );
}

function PreviewPanel({
  artifact,
  deployment,
  files,
  knowledgeBases,
  onClose,
  onSave,
  onDeploy,
  onCreateKb,
  onImportText,
  onRetrieve,
}: {
  artifact?: WorkspaceArtifact;
  deployment?: Deployment;
  files: UploadedFile[];
  knowledgeBases: KnowledgeBase[];
  onClose: () => void;
  onSave: (artifact: WorkspaceArtifact) => void;
  onDeploy: () => void;
  onCreateKb: (payload: {
    name: string;
    description: string;
    scope: string;
    visibility: string;
  }) => Promise<void>;
  onImportText: (
    kbId: string,
    payload: { title: string; content: string },
  ) => Promise<void>;
  onRetrieve: (kbId: string, query: string) => Promise<string>;
}) {
  const [tab, setTab] = useState("preview");
  const [draft, setDraft] = useState("");
  const [exportResult, setExportResult] = useState<{
    previewUrl?: string;
    previewText?: string;
    contentType: string;
    filename?: string;
  }>();

  useEffect(() => {
    setDraft(artifact?.code ?? "");
  }, [artifact?.id, artifact?.code]);

  if (!artifact) {
    return (
      <Sider
        width={460}
        className="preview-panel"
        data-testid="artifact-preview-panel"
      >
        <Empty description="点击聊天流中的预览产物卡片后展开预览、编辑、Diff、部署和资产面板" />
      </Sider>
    );
  }

  const previewDocument = buildPreviewDocument(draft);

  return (
    <Sider
      width={470}
      className="preview-panel"
      data-testid="artifact-preview-panel"
    >
      <Flex justify="space-between" align="center" className="preview-head">
        <div>
          <Text type="secondary">Artifact</Text>
          <Title level={4}>{artifact.title}</Title>
        </div>
        <Space>
          <Button onClick={onClose}>Close</Button>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={() => onSave({ ...artifact, code: draft })}
            data-testid="save-artifact"
          >
            保存
          </Button>
        </Space>
      </Flex>
      <Space wrap className="artifact-export-bar">
        {["zip", "html", "markdown", "json", "docx", "xlsx", "pptx"].map(
          (format) => (
            <Button
              key={format}
              size="small"
              onClick={async () => {
                const exported = await api.exportArtifact(artifact.id, format);
                setExportResult(exported);
                if (exported.previewUrl)
                  window.open(
                    exported.previewUrl,
                    "_blank",
                    "noopener,noreferrer",
                  );
              }}
            >
              {format.toUpperCase()}
            </Button>
          ),
        )}
        {exportResult?.filename && (
          <Tag color="blue">{exportResult.filename}</Tag>
        )}
      </Space>
      <Tabs
        data-testid="artifact-tabs"
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: "preview",
            label: <EyeOutlined />,
            children: (
              <div className="preview-frame-wrap">
                <iframe
                  title="artifact preview"
                  sandbox="allow-scripts"
                  srcDoc={previewDocument}
                />
              </div>
            ),
          },
          {
            key: "code",
            label: <CodeOutlined />,
            children: (
              <div className="code-pane">
                <Flex justify="space-between" align="center">
                  <Tag icon={<EditOutlined />}>Textarea fallback</Tag>
                  <Text type="secondary">{artifact.language}</Text>
                </Flex>
                <TextArea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  className="code-editor"
                  data-testid="artifact-code-editor"
                  aria-label="artifact-code-editor"
                />
              </div>
            ),
          },
          {
            key: "diff",
            label: <DiffOutlined />,
            children: (
              <div className="diff-pane">
                {diffLines(artifact.previousCode, draft).map((line, index) => (
                  <div
                    key={`${line.type}-${index}`}
                    className={`diff-line diff-${line.type}`}
                  >
                    <span>
                      {line.type === "add"
                        ? "+"
                        : line.type === "remove"
                          ? "-"
                          : line.type === "change"
                            ? "~"
                            : " "}
                    </span>
                    <code>{line.text}</code>
                  </div>
                ))}
              </div>
            ),
          },
          {
            key: "deploy",
            label: <RocketOutlined />,
            children: (
              <Card className="deploy-card" data-testid="deployment-card">
                <Space direction="vertical" size={14}>
                  <Tag
                    color={
                      deployment?.status === "ready" ||
                      deployment?.status === "deployed"
                        ? "success"
                        : "processing"
                    }
                    icon={<RocketOutlined />}
                  >
                    {deployment?.status ?? "idle"}
                  </Tag>
                  <Text strong>{deployment?.url ?? "尚未部署"}</Text>
                  <Text type="secondary">
                    Commit: {deployment?.commit ?? "pending"}
                  </Text>
                  <Progress percent={deployment ? 100 : 0} size="small" />
                  <Button
                    type="primary"
                    icon={<RocketOutlined />}
                    onClick={onDeploy}
                    data-testid="deploy-artifact"
                  >
                    部署当前版本
                  </Button>
                </Space>
              </Card>
            ),
          },
          {
            key: "assets",
            label: <DatabaseOutlined />,
            children: (
              <FilesKnowledgePanel
                files={files}
                knowledgeBases={knowledgeBases}
                onCreateKb={onCreateKb}
                onImportText={onImportText}
                onRetrieve={onRetrieve}
              />
            ),
          },
        ]}
      />
    </Sider>
  );
}

function BackgroundTasksButton({
  tasks,
  conversations,
  activeConversationId,
  onOpenConversation,
  onCreate,
  onCancel,
  onRefresh,
}: {
  tasks: AgentTask[];
  conversations: Conversation[];
  activeConversationId?: string;
  onOpenConversation: (conversationId: string) => void;
  onCreate: (prompt: string) => Promise<void>;
  onCancel: (task: AgentTask) => Promise<void>;
  onRefresh: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const conversationMap = useMemo(
    () => new Map(conversations.map((item) => [item.id, item.title])),
    [conversations],
  );
  const running = tasks.filter((task) => isTaskRunning(task.status));
  const recent = tasks.slice(0, 8);

  const create = async () => {
    const value = draft.trim();
    if (!value || !activeConversationId) return;
    setCreating(true);
    try {
      await onCreate(value);
      setDraft("");
      setOpen(false);
    } finally {
      setCreating(false);
    }
  };

  const content = (
    <div
      className="background-task-popover"
      data-testid="background-task-popover"
    >
      <Flex
        justify="space-between"
        align="center"
        className="background-task-head"
      >
        <Text type="secondary">后台任务</Text>
        <Text type="secondary">进行 {running.length}</Text>
      </Flex>
      {recent.length ? (
        <List
          className="background-task-list"
          dataSource={recent}
          renderItem={(task) => (
            <List.Item
              actions={
                isTaskRunning(task.status)
                  ? [
                      <Button
                        key="cancel"
                        size="small"
                        danger
                        onClick={(event) => {
                          event.stopPropagation();
                          onCancel(task);
                        }}
                      >
                        停止
                      </Button>,
                    ]
                  : []
              }
            >
              <button
                type="button"
                className="background-task-item"
                onClick={() =>
                  task.conversation_id &&
                  onOpenConversation(task.conversation_id)
                }
              >
                <Flex justify="space-between" gap={10} align="center">
                  <Text strong ellipsis>
                    {task.title}
                  </Text>
                  <Tag
                    color={
                      isTaskRunning(task.status)
                        ? "processing"
                        : task.status === "COMPLETED"
                          ? "success"
                          : "default"
                    }
                  >
                    {task.status}
                  </Tag>
                </Flex>
                <Progress
                  percent={Math.min(100, task.progress ?? 0)}
                  size="small"
                  showInfo={false}
                />
                <Text type="secondary" ellipsis>
                  {task.conversation_id
                    ? (conversationMap.get(task.conversation_id) ?? "关联会话")
                    : "独立任务"}{" "}
                  · {formatTime(task.updated_at ?? task.created_at)}
                </Text>
              </button>
            </List.Item>
          )}
        />
      ) : (
        <div className="background-task-empty">
          <div className="background-task-empty-icon">
            <ApiOutlined />
          </div>
          <Title level={4}>暂无生成中内容</Title>
          <Text type="secondary">可以随时对话，让 AI 为你生成哦</Text>
        </div>
      )}
      <Divider />
      <Space direction="vertical" className="full-width" size={8}>
        <TextArea
          rows={3}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="输入要放到当前会话后台执行的任务"
          data-testid="background-task-input"
        />
        <Flex justify="space-between" gap={8}>
          <Button onClick={onRefresh}>刷新</Button>
          <Button
            type="primary"
            loading={creating}
            disabled={!draft.trim() || !activeConversationId}
            onClick={create}
          >
            创建后台任务
          </Button>
        </Flex>
      </Space>
    </div>
  );

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottomRight"
      content={content}
    >
      <Badge count={running.length} size="small">
        <Button icon={<ApiOutlined />} data-testid="background-tasks">
          后台任务
        </Button>
      </Badge>
    </Popover>
  );
}

function Workbench({
  user,
  onLogout,
  routeWorkspaceId,
  routeConversationId,
  routeTab = "chat",
  onRouteChange,
  onRouteTabChange,
}: {
  user: User;
  onLogout: () => void;
  routeWorkspaceId?: string;
  routeConversationId?: string;
  routeTab?: string;
  onRouteChange: (
    workspaceId?: string,
    conversationId?: string,
    options?: { replace?: boolean },
  ) => void;
  onRouteTabChange: (
    tab: "chat" | "agents" | "workspace" | "settings",
    options?: { replace?: boolean },
  ) => void;
}) {
  const [currentUser, setCurrentUser] = useState(user);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [artifact, setArtifact] = useState<WorkspaceArtifact>();
  const [artifactPanelOpen, setArtifactPanelOpen] = useState(false);
  const [deployment, setDeployment] = useState<Deployment>();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [backgroundTasks, setBackgroundTasks] = useState<AgentTask[]>([]);
  const [localRunningConversationIds, setLocalRunningConversationIds] =
    useState<Set<string>>(() => new Set());
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string>();
  const [conversationCategories, setConversationCategories] = useState<
    string[]
  >(CONVERSATION_CATEGORY_OPTIONS);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [streamState, setStreamState] = useState<
    "idle" | "streaming" | "done" | "error"
  >("idle");
  const [agentDrawerOpen, setAgentDrawerOpen] = useState(false);
  const [workspacesOpen, setWorkspacesOpen] = useState(false);
  const [globalSettingsOpen, setGlobalSettingsOpen] = useState(false);
  const [conversationSettingsOpen, setConversationSettingsOpen] =
    useState(false);
  const [membersOpen, setMembersOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState<{
    open: boolean;
    group: boolean;
  }>({ open: false, group: false });
  const stopStreamRef = useRef<(() => void) | undefined>();
  const { message } = AntApp.useApp();

  const active = conversations.find((item) => item.id === activeId);
  const activeWorkspace =
    workspaces.find((workspace) => workspace.id === activeWorkspaceId) ??
    workspaces[0];
  const currentConversationIds = useMemo(
    () => new Set(conversations.map((item) => item.id)),
    [conversations],
  );
  const visibleBackgroundTasks = useMemo(
    () =>
      backgroundTasks.filter(
        (task) =>
          !task.conversation_id ||
          currentConversationIds.has(task.conversation_id),
      ),
    [backgroundTasks, currentConversationIds],
  );
  const runningConversationIds = useMemo(() => {
    const next = new Set(localRunningConversationIds);
    backgroundTasks.forEach((task) => {
      if (task.conversation_id && isTaskRunning(task.status))
        next.add(task.conversation_id);
    });
    return next;
  }, [backgroundTasks, localRunningConversationIds]);
  const categoryStorageKey = useMemo(
    () => `agenthub:conversation-categories:${activeWorkspaceId ?? "default"}`,
    [activeWorkspaceId],
  );
  const categoryNamesFromConversations = useMemo(
    () =>
      conversations.map((item) => item.folder || item.category || "Default"),
    [conversations],
  );

  const navigateToConversation = (
    workspaceId?: string,
    conversationId?: string,
    replace = false,
  ) => {
    onRouteChange(workspaceId, conversationId, { replace });
  };

  const selectWorkspace = (workspaceId?: string, replace = false) => {
    if (!workspaceId) return;
    setActiveWorkspaceId(workspaceId);
    setActiveId(undefined);
    navigateToConversation(workspaceId, undefined, replace);
  };

  const selectConversation = (conversationId?: string, replace = false) => {
    if (!conversationId) return;
    const target = conversations.find((item) => item.id === conversationId);
    const workspaceId =
      target?.workspace_id || activeWorkspaceId || activeWorkspace?.id;
    setActiveId(conversationId);
    navigateToConversation(workspaceId, conversationId, replace);
  };

  const openMainTab = (tab: "agents" | "workspace" | "settings") => {
    setAgentDrawerOpen(tab === "agents");
    setWorkspacesOpen(tab === "workspace");
    setGlobalSettingsOpen(tab === "settings");
    onRouteTabChange(tab);
  };

  const closeMainTab = (tab: "agents" | "workspace" | "settings") => {
    if (tab === "agents") setAgentDrawerOpen(false);
    if (tab === "workspace") setWorkspacesOpen(false);
    if (tab === "settings") setGlobalSettingsOpen(false);
    if (routeTab === tab) onRouteTabChange("chat");
  };

  const saveConversationCategories = (nextCategories: string[]) => {
    const merged = mergeConversationCategories(
      CONVERSATION_CATEGORY_OPTIONS,
      nextCategories,
    );
    setConversationCategories(merged);
    window.localStorage.setItem(
      categoryStorageKey,
      JSON.stringify({ version: 2, items: merged }),
    );
  };

  const addConversationCategory = (name: string) => {
    saveConversationCategories([...conversationCategories, name]);
    message.success(`分类「${name}」已创建`);
  };

  const loadAgents = async () => setAgents(await api.agents());
  const loadBackgroundTasks = async () => {
    const tasks = await api.tasks();
    setBackgroundTasks(tasks);
  };

  useEffect(() => {
    setCurrentUser(user);
  }, [user]);

  useEffect(() => {
    let stored: string[] = [];
    try {
      const raw = window.localStorage.getItem(categoryStorageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      if (Array.isArray(parsed)) {
        stored = parsed
          .map(String)
          .filter((name) => !LEGACY_DEFAULT_CONVERSATION_CATEGORIES.has(name));
      } else if (parsed && Array.isArray(parsed.items)) {
        stored = parsed.items.map(String);
      }
    } catch {
      stored = [];
    }
    setConversationCategories(
      mergeConversationCategories(CONVERSATION_CATEGORY_OPTIONS, stored),
    );
  }, [categoryStorageKey]);

  useEffect(() => {
    setConversationCategories((current) =>
      mergeConversationCategories(
        CONVERSATION_CATEGORY_OPTIONS,
        current,
        categoryNamesFromConversations,
      ),
    );
  }, [categoryNamesFromConversations]);

  useEffect(() => {
    Promise.all([api.agents(), api.knowledgeBases(), api.workspaces()]).then(
      ([nextAgents, kbs, nextWorkspaces]) => {
        setAgents(nextAgents);
        setKnowledgeBases(kbs);
        setWorkspaces(nextWorkspaces);
        const routeWorkspace = nextWorkspaces.find(
          (workspace) => workspace.id === routeWorkspaceId,
        );
        const nextWorkspaceId = routeWorkspace?.id ?? nextWorkspaces[0]?.id;
        if (nextWorkspaceId) {
          setActiveWorkspaceId(nextWorkspaceId);
          if (!routeWorkspaceId || routeWorkspaceId !== nextWorkspaceId)
            navigateToConversation(nextWorkspaceId, undefined, true);
        }
      },
    );
    loadBackgroundTasks().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!workspaces.length) return;
    const routeWorkspace = routeWorkspaceId
      ? workspaces.find((workspace) => workspace.id === routeWorkspaceId)
      : undefined;
    if (routeWorkspace) {
      if (activeWorkspaceId !== routeWorkspace.id) {
        setActiveWorkspaceId(routeWorkspace.id);
        setActiveId(undefined);
      }
      return;
    }
    const fallbackId =
      activeWorkspaceId &&
      workspaces.some((workspace) => workspace.id === activeWorkspaceId)
        ? activeWorkspaceId
        : workspaces[0]?.id;
    if (fallbackId) {
      if (activeWorkspaceId !== fallbackId) setActiveWorkspaceId(fallbackId);
      navigateToConversation(fallbackId, undefined, true);
    }
  }, [routeWorkspaceId, workspaces, activeWorkspaceId]);

  useEffect(() => {
    setAgentDrawerOpen(routeTab === "agents");
    setWorkspacesOpen(routeTab === "workspace");
    setGlobalSettingsOpen(routeTab === "settings");
  }, [routeTab]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadBackgroundTasks().catch(() => undefined);
    }, 3500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!activeWorkspaceId && workspaces.length) return;
    let cancelled = false;
    setConversations([]);
    setActiveId(undefined);
    setMessages([]);
    setArtifact(undefined);
    setArtifactPanelOpen(false);
    api.conversations(activeWorkspaceId).then((items) => {
      if (!cancelled) setConversations(items);
    });
    return () => {
      cancelled = true;
    };
  }, [activeWorkspaceId, workspaces.length]);

  useEffect(() => {
    if (!activeWorkspaceId) return;
    const scopedConversations = conversations.filter(
      (item) => (item.workspace_id || undefined) === activeWorkspaceId,
    );
    if (!scopedConversations.length) {
      setActiveId(undefined);
      if (routeConversationId)
        navigateToConversation(activeWorkspaceId, undefined, true);
      return;
    }
    const routeConversation = routeConversationId
      ? scopedConversations.find((item) => item.id === routeConversationId)
      : undefined;
    const currentConversation = activeId
      ? scopedConversations.find((item) => item.id === activeId)
      : undefined;
    const nextConversation =
      routeConversation ??
      currentConversation ??
      scopedConversations.find((item) => !item.archived) ??
      scopedConversations[0];
    if (!nextConversation) return;
    if (activeId !== nextConversation.id) setActiveId(nextConversation.id);
    const workspaceId = nextConversation.workspace_id || activeWorkspaceId;
    if (
      routeWorkspaceId !== workspaceId ||
      routeConversationId !== nextConversation.id
    ) {
      navigateToConversation(workspaceId, nextConversation.id, true);
    }
  }, [
    activeWorkspaceId,
    activeId,
    conversations,
    routeConversationId,
    routeWorkspaceId,
  ]);

  useEffect(() => {
    if (!activeId) return;
    setArtifactPanelOpen(false);
    setLoadingMessages(true);
    Promise.all([
      api.messages(activeId),
      api.artifact(activeId),
      api.files(activeId),
    ])
      .then(([nextMessages, nextArtifact, nextFiles]) => {
        setMessages(nextMessages);
        setArtifact(nextArtifact);
        setFiles(nextFiles);
      })
      .finally(() => setLoadingMessages(false));
  }, [activeId]);

  const patchConversation = async (
    item: Conversation,
    patch: Partial<Conversation>,
  ) => {
    const updated = await api.updateConversation(item.id, patch);
    const nextCategory =
      patch.folder || patch.category || updated.folder || updated.category;
    if (nextCategory)
      saveConversationCategories([...conversationCategories, nextCategory]);
    setConversations((current) =>
      current.map((conversation) =>
        conversation.id === item.id
          ? { ...conversation, ...updated }
          : conversation,
      ),
    );
  };

  const createConversation = async (payload: {
    title?: string;
    agentIds: string[];
    group: boolean;
    masterEnabled: boolean;
    folder: string;
  }) => {
    const created = await api.createConversationWithAgents({
      chat_type: payload.group ? "group" : "single",
      title: payload.title,
      participant_agent_ids: payload.agentIds,
      master_enabled: payload.masterEnabled,
      folder: payload.folder,
      category: payload.folder,
      workspace_id: activeWorkspaceId,
    });
    saveConversationCategories([...conversationCategories, payload.folder]);
    setConversations((current) => [created, ...current]);
    setActiveId(created.id);
    navigateToConversation(
      created.workspace_id || activeWorkspaceId,
      created.id,
    );
    setMessages([]);
    setCreateOpen({ open: false, group: false });
    message.success(payload.group ? "群聊已创建" : "会话已创建");
  };

  const appendAssistantStream = async (
    conversationId: string,
    prompt: string,
  ) => {
    const assistant = makeMessage({
      conversationId,
      role: "assistant",
      kind: "text",
      author: "Master Agent",
      content: "",
      streamState: "streaming",
    });
    setMessages((current) => [...current, assistant]);
    setStreamState("streaming");
    setLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.add(conversationId);
      return next;
    });
    setConversations((current) =>
      current.map((item) =>
        item.id === conversationId
          ? { ...item, updatedAt: new Date().toISOString(), unread: 0 }
          : item,
      ),
    );
    stopStreamRef.current = undefined;

    let rawBuffer = "";
    let completedPreview = "";
    try {
      await api.streamAssistantReply(
        conversationId,
        (delta) => {
          rawBuffer += delta;
          const visible = stripInternalAgentOutput(rawBuffer);
          setMessages((current) =>
            current.map((item) =>
              item.id === assistant.id ? { ...item, content: visible } : item,
            ),
          );
        },
        () => {
          setMessages((current) =>
            current.map((item) =>
              item.id === assistant.id
                ? { ...item, streamState: "done" }
                : item,
            ),
          );
        },
        (stop) => {
          stopStreamRef.current = stop;
        },
      );
      setMessages((current) =>
        current.map((item) =>
          item.id === assistant.id ? { ...item, streamState: "done" } : item,
        ),
      );
      setStreamState("done");
      const [freshMessages, freshArtifact] = await Promise.all([
        api.messages(conversationId),
        api.artifact(conversationId),
      ]).catch(() => [undefined, undefined]);
      if (freshMessages) {
        const cleanMessages = freshMessages.map((item) =>
          item.role === "assistant" && item.kind === "text"
            ? { ...item, content: stripInternalAgentOutput(item.content) }
            : item,
        );
        const hasPreviewCard = cleanMessages.some(
          (item) => item.kind === "preview_card",
        );
        setMessages(
          hasPreviewCard || !freshArtifact
            ? cleanMessages
            : [
                ...cleanMessages,
                makeMessage({
                  conversationId,
                  role: "assistant",
                  kind: "preview_card",
                  author: "Artifact Agent",
                  content: `预览产物：${freshArtifact.title}`,
                  streamState: "done",
                }),
              ],
        );
        const lastAssistant = [...cleanMessages]
          .reverse()
          .find((item) => item.role === "assistant" && item.kind === "text");
        const previewText =
          stripInternalAgentOutput(lastAssistant?.content ?? rawBuffer) ||
          "已完成";
        completedPreview = previewText.slice(0, 120);
        setConversations((current) =>
          current.map((item) =>
            item.id === conversationId
              ? {
                  ...item,
                  lastMessage: completedPreview,
                  updatedAt: new Date().toISOString(),
                }
              : item,
          ),
        );
      }
      if (freshArtifact) setArtifact(freshArtifact);
    } catch (error) {
      const fallbackPreview =
        stripInternalAgentOutput(rawBuffer).slice(0, 120) ||
        "回复暂未完成，请稍后刷新。";
      completedPreview = fallbackPreview;
      setStreamState("error");
      setMessages((current) =>
        current.map((item) =>
          item.id === assistant.id
            ? {
                ...item,
                streamState: "error",
                content: stripInternalAgentOutput(rawBuffer) || fallbackPreview,
              }
            : item,
        ),
      );
      throw error;
    } finally {
      setLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      if (completedPreview) {
        setConversations((current) =>
          current.map((item) =>
            item.id === conversationId && item.lastMessage === "正在回答..."
              ? {
                  ...item,
                  lastMessage: completedPreview,
                  updatedAt: new Date().toISOString(),
                }
              : item,
          ),
        );
      }
      loadBackgroundTasks().catch(() => undefined);
    }
  };

  const appendConversationStream = async (
    conversationId: string,
    prompt: string,
  ) => {
    const targetConversation =
      conversations.find((item) => item.id === conversationId) ?? active;
    const agentParticipants =
      targetConversation?.participants.filter(
        (item) => item.participant_type === "agent" && item.agent_id,
      ) ?? [];
    const tempIdsByAgentId = new Map<string, string>();
    const tempIdsByAuthor = new Map<string, string>();

    const normalizeIncomingMessage = (incoming: ChatMessage): ChatMessage => ({
      ...incoming,
      conversationId:
        incoming.conversationId ??
        (incoming as ChatMessage & { conversation_id?: string })
          .conversation_id ??
        conversationId,
      role: incoming.role ?? "assistant",
      kind: incoming.kind ?? "text",
      author:
        incoming.author ||
        (incoming as ChatMessage & { sender_name?: string }).sender_name ||
        "Agent",
      content:
        incoming.role === "assistant" && incoming.kind === "text"
          ? stripInternalAgentOutput(incoming.content)
          : incoming.content,
      createdAt:
        incoming.createdAt ??
        (incoming as ChatMessage & { created_at?: string }).created_at ??
        new Date().toISOString(),
      streamState:
        incoming.role === "assistant" && incoming.kind === "text"
          ? "done"
          : incoming.streamState,
    });

    const ensureStreamingMessage = (
      messageId: string,
      author: string,
      agentId?: string,
    ) => {
      setMessages((current) => {
        if (current.some((item) => item.id === messageId)) return current;
        const tempId =
          (agentId && tempIdsByAgentId.get(agentId)) ||
          tempIdsByAuthor.get(author);
        if (tempId) {
          if (agentId) tempIdsByAgentId.set(agentId, messageId);
          tempIdsByAuthor.set(author, messageId);
          return current.map((item) =>
            item.id === tempId
              ? {
                  ...item,
                  id: messageId,
                  sender_id: agentId,
                  author,
                  rawContent: { ...(item.rawContent ?? {}), agent_id: agentId },
                  streamState: "streaming",
                }
              : item,
          );
        }
        return [
          ...current,
          makeMessage({
            conversationId,
            role: "assistant",
            kind: "text",
            author,
            content: "",
            rawContent: agentId ? { agent_id: agentId } : {},
            streamState: "streaming",
          }),
        ].map((item) =>
          item.id.startsWith("local-") &&
          item.author === author &&
          !item.content
            ? { ...item, id: messageId }
            : item,
        );
      });
    };

    const upsertFinalMessage = (incoming: ChatMessage) => {
      const normalized = normalizeIncomingMessage(incoming);
      const agentId =
        normalized.sender_id ||
        (normalized.rawContent?.agent_id as string | undefined);
      setMessages((current) => {
        if (current.some((item) => item.id === normalized.id)) {
          return current.map((item) =>
            item.id === normalized.id ? { ...item, ...normalized } : item,
          );
        }
        const tempId =
          (agentId && tempIdsByAgentId.get(agentId)) ||
          tempIdsByAuthor.get(normalized.author);
        if (tempId) {
          if (agentId) tempIdsByAgentId.set(agentId, normalized.id);
          tempIdsByAuthor.set(normalized.author, normalized.id);
          return current.map((item) =>
            item.id === tempId ? { ...item, ...normalized } : item,
          );
        }
        return [...current, normalized];
      });
    };

    if (agentParticipants.length === 1) {
      const participant = agentParticipants[0];
      const author = participantName(participant);
      const agentId = participant.agent_id ?? participant.id ?? author;
      const placeholder = makeMessage({
        conversationId,
        role: "assistant",
        kind: "text",
        author,
        content: "",
        rawContent: {
          agent_id: participant.agent_id,
          participant_id: participant.id,
        },
        streamState: "streaming",
      });
      tempIdsByAgentId.set(agentId, placeholder.id);
      tempIdsByAuthor.set(author, placeholder.id);
      setMessages((current) => [...current, placeholder]);
    }

    setStreamState("streaming");
    setLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.add(conversationId);
      return next;
    });
    setConversations((current) =>
      current.map((item) =>
        item.id === conversationId
          ? { ...item, updatedAt: new Date().toISOString(), unread: 0 }
          : item,
      ),
    );
    stopStreamRef.current = undefined;

    let rawBuffer = "";
    let completedPreview = "";
    try {
      await api.streamAssistantReply(conversationId, {
        onMessageStart: (payload) => {
          const messageId = String(
            payload.agent_message_id ||
              payload.message_id ||
              `stream-${Date.now()}`,
          );
          const agentId = payload.agent_id
            ? String(payload.agent_id)
            : undefined;
          const author = String(
            payload.agent_name ||
              payload.sender_name ||
              (agentId ? "Agent" : "Assistant"),
          );
          ensureStreamingMessage(messageId, author, agentId);
        },
        onDelta: (delta, payload) => {
          rawBuffer += delta;
          const messageId = String(
            payload.agent_message_id || payload.message_id || "",
          );
          if (!messageId) return;
          ensureStreamingMessage(
            messageId,
            String(payload.agent_name || "Agent"),
            payload.agent_id ? String(payload.agent_id) : undefined,
          );
          setMessages((current) =>
            current.map((item) =>
              item.id === messageId
                ? {
                    ...item,
                    content: stripInternalAgentOutput(
                      `${item.content}${delta}`,
                    ),
                    streamState: "streaming",
                  }
                : item,
            ),
          );
        },
        onMessageUpdated: upsertFinalMessage,
        onMessageNew: (incoming) => {
          if (incoming.kind === "preview_card") upsertFinalMessage(incoming);
        },
        onDone: () => {
          setMessages((current) =>
            current.map((item) =>
              item.streamState === "streaming"
                ? { ...item, streamState: "done" }
                : item,
            ),
          );
        },
        onControl: (stop) => {
          stopStreamRef.current = stop;
        },
      });
      setStreamState("done");
      const [freshMessages, freshArtifact] = await Promise.all([
        api.messages(conversationId),
        api.artifact(conversationId),
      ]).catch(() => [undefined, undefined]);
      if (freshMessages) {
        const cleanMessages = freshMessages.map((item) =>
          item.role === "assistant" && item.kind === "text"
            ? {
                ...item,
                content: stripInternalAgentOutput(item.content),
                streamState: "done" as const,
              }
            : item,
        );
        const hasPreviewCard = cleanMessages.some(
          (item) => item.kind === "preview_card",
        );
        setMessages(
          hasPreviewCard || !freshArtifact
            ? cleanMessages
            : [
                ...cleanMessages,
                makeMessage({
                  conversationId,
                  role: "assistant",
                  kind: "preview_card",
                  author: "Artifact Agent",
                  content: `预览产物：${freshArtifact.title}`,
                  streamState: "done",
                }),
              ],
        );
        const lastAssistant = [...cleanMessages]
          .reverse()
          .find((item) => item.role === "assistant" && item.kind === "text");
        completedPreview = (
          lastAssistant?.content ||
          stripInternalAgentOutput(rawBuffer) ||
          "done"
        ).slice(0, 120);
        setConversations((current) =>
          current.map((item) =>
            item.id === conversationId
              ? {
                  ...item,
                  lastMessage: completedPreview,
                  updatedAt: new Date().toISOString(),
                }
              : item,
          ),
        );
      }
      if (freshArtifact) setArtifact(freshArtifact);
    } catch (error) {
      const fallbackPreview =
        stripInternalAgentOutput(rawBuffer).slice(0, 120) || "reply failed";
      completedPreview = fallbackPreview;
      setStreamState("error");
      setMessages((current) =>
        current.map((item) =>
          item.streamState === "streaming"
            ? {
                ...item,
                streamState: "error",
                content: item.content || fallbackPreview,
              }
            : item,
        ),
      );
      throw error;
    } finally {
      setLocalRunningConversationIds((current) => {
        const next = new Set(current);
        next.delete(conversationId);
        return next;
      });
      if (completedPreview) {
        setConversations((current) =>
          current.map((item) =>
            item.id === conversationId && item.lastMessage === "正在回答..."
              ? {
                  ...item,
                  lastMessage: completedPreview,
                  updatedAt: new Date().toISOString(),
                }
              : item,
          ),
        );
      }
      loadBackgroundTasks().catch(() => undefined);
    }
  };

  const stopStreaming = async () => {
    if (!activeId) return;
    stopStreamRef.current?.();
    stopStreamRef.current = undefined;
    setStreamState("done");
    setLocalRunningConversationIds((current) => {
      const next = new Set(current);
      next.delete(activeId);
      return next;
    });
    setConversations((current) =>
      current.map((item) =>
        item.id === activeId
          ? {
              ...item,
              lastMessage: "已停止本次响应。",
              updatedAt: new Date().toISOString(),
            }
          : item,
      ),
    );
    setMessages((current) =>
      current.map((item) =>
        item.streamState === "streaming"
          ? {
              ...item,
              streamState: "done",
              content: item.content || "已停止接收本次回复。",
            }
          : item,
      ),
    );
    await api.cancelAssistantReply(activeId).catch(() => undefined);
    await loadBackgroundTasks().catch(() => undefined);
    message.info("已停止本次响应");
  };

  const send = async (
    content: string,
    quoted?: ChatMessage,
    attachments: UploadedFile[] = [],
  ) => {
    if (!activeId) return;
    const conversationId = activeId;
    const localAttachments: MessageAttachment[] = attachments.map((file) => ({
      file_id: file.file_id ?? file.id,
      id: file.id,
      filename: file.filename,
      original_filename: file.original_filename,
      content_type: file.content_type,
      size: file.size,
      parse_status: file.parse_status,
      public_url: file.public_url,
    }));
    const localMessage = makeMessage({
      conversationId,
      role: "user",
      kind: "text",
      author: currentUser.name,
      content,
      rawContent: { text: content, attachments: localAttachments },
      attachments: localAttachments,
      quotedMessageId: quoted?.id,
    });
    setMessages((current) => [...current, localMessage]);
    setConversations((current) =>
      current.map((item) =>
        item.id === conversationId
          ? {
              ...item,
              lastMessage: content,
              updatedAt: new Date().toISOString(),
              unread: 0,
            }
          : item,
      ),
    );
    const streamPromise = appendConversationStream(
      conversationId,
      content,
    ).catch(() => setStreamState("error"));
    try {
      const userMessage = await api.sendMessage(
        conversationId,
        content,
        quoted?.id,
        attachments,
      );
      setMessages((current) =>
        current.map((item) =>
          item.id === localMessage.id ? userMessage : item,
        ),
      );
      if (isLikelyArtifactRequest(content)) {
        const freshArtifact = await api
          .artifact(conversationId)
          .catch(() => undefined);
        if (freshArtifact) {
          setArtifact(freshArtifact);
          setMessages((current) => {
            const exists = current.some(
              (item) =>
                item.kind === "preview_card" &&
                item.rawContent?.artifact_id === freshArtifact.id,
            );
            if (exists) return current;
            return [
              ...current,
              makeMessage({
                conversationId,
                role: "assistant",
                kind: "preview_card",
                author: "Artifact Agent",
                content: `预览产物：${freshArtifact.title}`,
                rawContent: { artifact_id: freshArtifact.id },
                streamState: "done",
              }),
            ];
          });
          setConversations((current) =>
            current.map((item) =>
              item.id === conversationId
                ? {
                    ...item,
                    lastMessage:
                      "已生成产物卡片，可点击后在右侧预览、编辑和部署。",
                    updatedAt: new Date().toISOString(),
                  }
                : item,
            ),
          );
        }
      }
    } catch (error) {
      stopStreamRef.current?.();
      void streamPromise;
      setMessages((current) =>
        current.map((item) =>
          item.id === localMessage.id
            ? {
                ...item,
                kind: "error",
                content: `${content}\n\n发送失败：${error instanceof Error ? error.message : "网络异常"}`,
              }
            : item,
        ),
      );
      message.error("消息发送失败");
    }
  };

  const regenerate = (source: ChatMessage) => {
    if (!activeId) return;
    appendConversationStream(
      activeId,
      `请重新生成这条回复：${source.content}`,
    ).catch(() => setStreamState("error"));
  };

  const saveArtifact = async (next: WorkspaceArtifact) => {
    const saved = await api.saveArtifact(next);
    setArtifact(saved);
    message.success("产物已保存");
  };

  const deploy = async () => {
    if (!activeId) return;
    setDeployment({
      id: "pending",
      status: "building",
      commit: "pending",
      updatedAt: new Date().toISOString(),
    });
    const result = await api.deploy(activeId, artifact?.id);
    setDeployment(result);
    message.success("部署任务已提交");
  };

  const uploadFile = async (file: File) => {
    const uploaded = await api.uploadFile(file, activeId);
    setFiles((current) => [uploaded, ...current]);
    message.success("文件已加入输入框，发送后会进入模型上下文");
    return uploaded;
  };

  const openArtifactPreview = async (source?: ChatMessage) => {
    if (!activeId) return;
    const artifactId =
      typeof source?.rawContent?.artifact_id === "string"
        ? source.rawContent.artifact_id
        : undefined;
    const current =
      (artifactId ? await api.artifactById(artifactId) : undefined) ??
      artifact ??
      (await api.artifact(activeId));
    const nextArtifact =
      current ??
      (source?.kind === "preview_card"
        ? {
            id: artifactId ?? `local-${activeId}`,
            conversationId: activeId,
            title:
              source.content.replace(/^预览产物[:：]\s*/, "") ||
              "AgentHub artifact",
            language: "html",
            code: "<main><h1>Artifact preview</h1><p>产物索引已恢复，请刷新或重新生成以查看完整文件。</p></main>",
            previousCode: "",
            updatedAt: new Date().toISOString(),
          }
        : undefined);
    if (!nextArtifact) {
      message.warning("当前会话还没有可预览产物");
      return;
    }
    setArtifact(nextArtifact);
    setArtifactPanelOpen(true);
  };

  return (
    <Layout className="workbench">
      <ConversationSidebar
        conversations={conversations}
        activeId={activeId}
        runningConversationIds={runningConversationIds}
        categoryOptions={conversationCategories}
        onSelect={selectConversation}
        onCreate={(group) => setCreateOpen({ open: true, group })}
        onCreateCategory={addConversationCategory}
        onTogglePin={(item) =>
          patchConversation(item, { pinned: !item.pinned })
        }
        onToggleArchive={(item) =>
          patchConversation(item, { archived: !item.archived })
        }
        onEdit={(item, patch) => patchConversation(item, patch)}
        onDelete={(item) => {
          Modal.confirm({
            title: "删除归档会话",
            content: `确认删除「${item.title}」？删除后会从列表移除。`,
            okText: "删除",
            okButtonProps: { danger: true },
            onOk: async () => {
              await api.deleteConversation(item.id);
              setConversations((current) =>
                current.filter((conversation) => conversation.id !== item.id),
              );
              if (activeId === item.id) {
                const nextConversation = conversations.find(
                  (conversation) => conversation.id !== item.id,
                );
                setActiveId(nextConversation?.id);
                navigateToConversation(
                  nextConversation?.workspace_id || activeWorkspaceId,
                  nextConversation?.id,
                  true,
                );
              }
              message.success("归档会话已删除");
            },
          });
        }}
      />
      <Layout className="center-layout">
        <div className="topbar">
          <Space>
            <Avatar>
              {currentUser.avatar ?? currentUser.name.slice(0, 1)}
            </Avatar>
            <div>
              <Text strong>{currentUser.name}</Text>
              <br />
              <Text type="secondary">
                {currentUser.role === "demo" ? "演示用户" : "成员"}
              </Text>
            </div>
          </Space>
          <Space>
            <Select
              style={{ width: 220 }}
              value={activeWorkspace?.id}
              placeholder="选择工作区"
              onChange={(value) => selectWorkspace(value)}
              options={workspaces.map((workspace) => ({
                label: workspace.name,
                value: workspace.id,
              }))}
            />
            <Button
              icon={<AppstoreOutlined />}
              onClick={() => openMainTab("workspace")}
              data-testid="workspace-panel"
            >
              工作区
            </Button>
            <BackgroundTasksButton
              tasks={visibleBackgroundTasks}
              conversations={conversations}
              activeConversationId={activeId}
              onOpenConversation={selectConversation}
              onCreate={async (prompt) => {
                await send(prompt);
                await loadBackgroundTasks().catch(() => undefined);
              }}
              onCancel={async (task) => {
                await api.cancelTask(task.id);
                if (task.conversation_id) {
                  await api
                    .cancelAssistantReply(task.conversation_id)
                    .catch(() => undefined);
                  setLocalRunningConversationIds((current) => {
                    const next = new Set(current);
                    if (task.conversation_id) next.delete(task.conversation_id);
                    return next;
                  });
                }
                await loadBackgroundTasks();
                message.info("后台任务已停止");
              }}
              onRefresh={loadBackgroundTasks}
            />
            <Button
              icon={<ToolOutlined />}
              onClick={() => openMainTab("settings")}
              data-testid="global-settings"
            >
              设置
            </Button>
            <Button
              icon={<RobotOutlined />}
              onClick={() => openMainTab("agents")}
              data-testid="agent-directory"
            >
              Agent 广场
            </Button>
            <Button onClick={onLogout}>退出</Button>
          </Space>
        </div>
        <ChatPanel
          user={currentUser}
          active={active}
          messages={messages}
          loading={loadingMessages}
          streamState={streamState}
          onSend={send}
          onRegenerate={regenerate}
          onOpenMembers={() => setMembersOpen(true)}
          onOpenSettings={() => setConversationSettingsOpen(true)}
          onUploadFile={uploadFile}
          onOpenPreview={openArtifactPreview}
          onStopStreaming={stopStreaming}
        />
      </Layout>
      {artifactPanelOpen && artifact && (
        <PreviewPanel
          artifact={artifact}
          deployment={deployment}
          files={files}
          knowledgeBases={knowledgeBases}
          onClose={() => setArtifactPanelOpen(false)}
          onSave={saveArtifact}
          onDeploy={deploy}
          onCreateKb={async (payload) => {
            const created = await api.createKnowledgeBase(payload);
            setKnowledgeBases((current) => [created, ...current]);
            message.success("知识库已创建");
          }}
          onImportText={async (kbId, payload) => {
            await api.importKnowledgeText(kbId, payload);
            setKnowledgeBases(await api.knowledgeBases());
            message.success("文档已索引");
          }}
          onRetrieve={async (kbId, query) => {
            const result = await api.retrieveKnowledge(kbId, query);
            return result.context;
          }}
        />
      )}
      <AgentDirectoryDrawer
        open={agentDrawerOpen}
        agents={agents}
        onClose={() => closeMainTab("agents")}
        onRefresh={loadAgents}
        onCreateAgent={(agent) => setAgents((current) => [agent, ...current])}
        onUpdateAgent={(agent) =>
          setAgents((current) =>
            current.map((item) => (item.id === agent.id ? agent : item)),
          )
        }
        onDeleteAgent={async (agent) => {
          await api.deleteAgent(agent.id);
          setAgents((current) =>
            current.filter((item) => item.id !== agent.id),
          );
        }}
        onTestAgent={async (agentId, text) =>
          (await api.testAgent(agentId, text)).response
        }
      />
      <MembersDrawer
        open={membersOpen}
        active={active}
        agents={agents}
        onClose={() => setMembersOpen(false)}
        onAddAgents={async (ids) => {
          if (!activeId) return;
          try {
            const updated = await api.addParticipants(activeId, ids);
            setConversations((current) =>
              current.map((item) => (item.id === activeId ? updated : item)),
            );
            message.success("成员已加入");
          } catch (error) {
            message.error(
              error instanceof Error ? error.message : "成员加入失败",
            );
          }
        }}
        onRemoveParticipant={async (participant) => {
          if (!activeId || !participant.id) return;
          const updated = await api.removeParticipant(activeId, participant.id);
          setConversations((current) =>
            current.map((item) => (item.id === activeId ? updated : item)),
          );
          message.success("成员已移除");
        }}
      />
      <ConversationSettingsDrawer
        open={conversationSettingsOpen}
        active={active}
        agents={agents}
        categoryOptions={conversationCategories}
        onClose={() => setConversationSettingsOpen(false)}
        onSaveConversation={patchConversation}
      />
      <CreateConversationModal
        open={createOpen.open}
        group={createOpen.group}
        agents={agents}
        categoryOptions={conversationCategories}
        onCancel={() => setCreateOpen({ open: false, group: false })}
        onCreate={createConversation}
      />
      <GlobalSettingsDrawer
        open={globalSettingsOpen}
        user={currentUser}
        onClose={() => closeMainTab("settings")}
        onUserUpdated={(nextUser) => {
          setCurrentUser(nextUser);
        }}
      />
      <PlatformControlDrawer
        open={workspacesOpen}
        workspaces={workspaces}
        activeConversation={active}
        onClose={() => closeMainTab("workspace")}
        onCreateWorkspace={async (payload) => {
          const created = await api.createWorkspace(payload);
          setWorkspaces((current) => [created, ...current]);
          setActiveWorkspaceId(created.id);
          navigateToConversation(created.id);
          message.success("工作区已创建");
        }}
        onCreateProject={async (workspaceId, payload) => {
          const project = await api.createProject(workspaceId, payload);
          setWorkspaces((current) =>
            current.map((workspace) =>
              workspace.id === workspaceId
                ? { ...workspace, project_count: workspace.project_count + 1 }
                : workspace,
            ),
          );
          message.success("项目已创建");
          return project;
        }}
        onLoadProjects={api.projects}
        onSaveProjectFile={async (projectId, payload) => {
          await api.saveProjectFile(projectId, payload);
          message.success("项目文件版本已保存");
        }}
      />
    </Layout>
  );
}

const MAIN_TABS = new Set(["chat", "agents", "workspace", "settings"]);

function normalizeMainTab(
  value: string | null,
): "chat" | "agents" | "workspace" | "settings" {
  return MAIN_TABS.has(value ?? "")
    ? (value as "chat" | "agents" | "workspace" | "settings")
    : "chat";
}

function LoginRoute({
  user,
  onLogin,
}: {
  user?: User;
  onLogin: (user: User) => void;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  if (user) return <Navigate to="/app" replace />;
  return (
    <LoginScreen
      onLogin={(nextUser) => {
        onLogin(nextUser);
        const from = (
          location.state as {
            from?: { pathname?: string; search?: string };
          } | null
        )?.from;
        const target =
          from?.pathname && from.pathname !== "/login"
            ? `${from.pathname}${from.search ?? ""}`
            : "/app";
        navigate(target, { replace: true });
      }}
    />
  );
}

function WorkbenchRoute({
  user,
  onLogout,
}: {
  user?: User;
  onLogout: () => void;
}) {
  const params = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;

  const routeTab = normalizeMainTab(searchParams.get("tab"));
  const routeWorkspaceId = params.workspaceId
    ? decodeURIComponent(params.workspaceId)
    : undefined;
  const routeConversationId = params.conversationId
    ? decodeURIComponent(params.conversationId)
    : undefined;
  const buildSearch = (tab = routeTab) =>
    tab && tab !== "chat" ? `?tab=${encodeURIComponent(tab)}` : "";

  return (
    <Workbench
      user={user}
      onLogout={onLogout}
      routeWorkspaceId={routeWorkspaceId}
      routeConversationId={routeConversationId}
      routeTab={routeTab}
      onRouteChange={(workspaceId, conversationId, options) => {
        const path = workspaceId
          ? conversationId
            ? `/app/${encodeURIComponent(workspaceId)}/c/${encodeURIComponent(conversationId)}`
            : `/app/${encodeURIComponent(workspaceId)}`
          : "/app";
        navigate(`${path}${buildSearch()}`, { replace: options?.replace });
      }}
      onRouteTabChange={(tab, options) => {
        navigate(`${location.pathname}${buildSearch(tab)}`, {
          replace: options?.replace,
        });
      }}
    />
  );
}

function RoutedApp() {
  const [user, setUser] = useState<User>();
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    const token = window.localStorage.getItem("agenthub_token");
    if (!token) {
      setAuthReady(true);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => window.localStorage.removeItem("agenthub_token"))
      .finally(() => setAuthReady(true));
  }, []);

  if (!authReady) {
    return (
      <AntApp>
        <main className="login-shell">
          <Spin tip="Restoring session..." />
        </main>
      </AntApp>
    );
  }

  return (
    <AntApp>
      <Routes>
        <Route
          path="/login"
          element={<LoginRoute user={user} onLogin={setUser} />}
        />
        <Route
          path="/app"
          element={
            <WorkbenchRoute
              user={user}
              onLogout={() => {
                api.logout().finally(() => setUser(undefined));
              }}
            />
          }
        />
        <Route
          path="/app/:workspaceId"
          element={
            <WorkbenchRoute
              user={user}
              onLogout={() => {
                api.logout().finally(() => setUser(undefined));
              }}
            />
          }
        />
        <Route
          path="/app/:workspaceId/c/:conversationId"
          element={
            <WorkbenchRoute
              user={user}
              onLogout={() => {
                api.logout().finally(() => setUser(undefined));
              }}
            />
          }
        />
        <Route
          path="*"
          element={<Navigate to={user ? "/app" : "/login"} replace />}
        />
      </Routes>
    </AntApp>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <RoutedApp />
    </BrowserRouter>
  );
}
