import { useMemo, useState } from "react";
import {
  CaretDownOutlined,
  CaretRightOutlined,
  DeleteOutlined,
  EditOutlined,
  FolderAddOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PlusOutlined,
  PushpinFilled,
  PushpinOutlined,
  SearchOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import {
  Avatar,
  Badge,
  Button,
  Empty,
  Flex,
  Form,
  Input,
  Layout,
  Modal,
  Segmented,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { api } from "@/api";
import { mergeConversationCategories } from "@/lib/conversation";
import { formatTime } from "@/lib/format";
import type { Agent, Conversation, User } from "@/types";
import { message } from "antd";

const { Sider } = Layout;
const { Text, Title } = Typography;
const { TextArea } = Input;

export function ConversationSidebar({
  currentUser,
  conversations,
  activeId,
  runningConversationIds,
  categoryOptions,
  agents,
  onSelect,
  onCreate,
  onCreateCategory,
  onTogglePin,
  onToggleArchive,
  onDelete,
  onEdit,
}: {
  currentUser: User;
  conversations: Conversation[];
  activeId?: string;
  runningConversationIds: Set<string>;
  categoryOptions: string[];
  agents: Agent[];
  onSelect: (id: string) => void;
  onCreate: () => void;
  onCreateCategory: (name: string) => void;
  onTogglePin: (item: Conversation) => void;
  onToggleArchive: (item: Conversation) => void;
  onDelete: (item: Conversation) => void;
  onEdit: (item: Conversation, patch: Partial<Conversation>) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"active" | "archived">("active");
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(
    new Set(),
  );
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [editing, setEditing] = useState<Conversation>();
  const [editForm] = Form.useForm();
  const [collapsed, setCollapsed] = useState(false);
  const [addingAgent, setAddingAgent] = useState(false);

  const selectCategoryOptions = useMemo(() => {
    const existing = conversations.map(
      (item) => item.folder || item.category || "Default",
    );
    return mergeConversationCategories(categoryOptions, existing).map(
      (name) => ({ label: name, value: name }),
    );
  }, [categoryOptions, conversations]);

  const filtered = useMemo(() => {
    return conversations
      .filter((item) =>
        filter === "archived" ? item.archived : !item.archived,
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
  }, [conversations, filter, query]);

  const treeData = useMemo(() => {
    const root: Conversation[] = [];
    const groups: Record<string, Conversation[]> = {};

    for (const item of filtered) {
      const cat = item.folder || item.category;
      if (cat) {
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(item);
      } else {
        root.push(item);
      }
    }

    const folders = Object.entries(groups)
      .map(([name, items]) => ({
        name,
        items: items.sort(
          (a, b) =>
            Number(b.pinned) - Number(a.pinned) ||
            +new Date(b.updatedAt) - +new Date(a.updatedAt),
        ),
        latestUpdated: Math.max(
          ...items.map((i) => +new Date(i.updatedAt)),
        ),
      }))
      .sort((a, b) => b.latestUpdated - a.latestUpdated);

    const sortedRoot = root.sort(
      (a, b) =>
        Number(b.pinned) - Number(a.pinned) ||
        +new Date(b.updatedAt) - +new Date(a.updatedAt),
    );

    return { folders, root: sortedRoot };
  }, [filtered]);

  const toggleFolder = (name: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const submitNewFolder = () => {
    const name = newFolderName.trim();
    if (!name) return;
    onCreateCategory(name);
    setExpandedFolders((prev) => new Set(prev).add(name));
    setNewFolderName("");
    setCreatingFolder(false);
  };

  const renderConversationItem = (item: Conversation) => {
    const running = runningConversationIds.has(item.id);
    return (
      <div
        key={item.id}
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
                ? `${item.participants.filter((p) => p.participant_type === "agent" && !p.left_at).length} Agent`
                : "单聊"}
            </Tag>
            {item.tags.map((tag) => (
              <Tag key={tag}>{tag}</Tag>
            ))}
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
  };

  return (
    <Sider
      width={320}
      collapsed={collapsed}
      collapsedWidth={52}
      className="sidebar"
    >
      {collapsed ? (
        <div className="sidebar-collapsed">
          <Tooltip title="展开侧边栏">
            <Button
              type="text"
              size="small"
              icon={<MenuUnfoldOutlined />}
              onClick={() => setCollapsed(false)}
            />
          </Tooltip>
          <Tooltip title="创建聊天">
            <Button
              shape="circle"
              type="primary"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => onCreate()}
              data-testid="new-chat"
            />
          </Tooltip>
        </div>
      ) : (
        <>
          <div className="sidebar-user">
            <Avatar size="large" src={currentUser.avatar_url ?? currentUser.avatar}>
              {currentUser.name.slice(0, 1)}
            </Avatar>
            <div className="sidebar-user-info">
              <Text strong ellipsis>
                {currentUser.name}
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {currentUser.role === "demo" ? "演示用户" : "成员"}
              </Text>
            </div>
          </div>
          <div className="sidebar-head">
            <div>
              <Text type="secondary">Workspace</Text>
              <Title level={3}>会话</Title>
            </div>
            <Space>
              <Tooltip title="创建聊天">
                <Button
                  shape="circle"
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => onCreate()}
                  data-testid="new-chat"
                />
              </Tooltip>
              <Tooltip title="收起侧边栏">
                <Button
                  type="text"
                  icon={<MenuFoldOutlined />}
                  onClick={() => setCollapsed(true)}
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
      <div className="sidebar-toolbar">
        <Text type="secondary">会话列表</Text>
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
      <div className="conversation-list">
        {treeData.folders.length === 0 && treeData.root.length === 0 && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="暂无会话"
          />
        )}
        {treeData.folders.map((folder) => {
          const expanded = expandedFolders.has(folder.name);
          return (
            <div key={folder.name} className="folder-tree-node">
              <div
                className="folder-tree-header"
                onClick={() => toggleFolder(folder.name)}
              >
                {expanded ? (
                  <CaretDownOutlined />
                ) : (
                  <CaretRightOutlined />
                )}
                <FolderOpenOutlined />
                <span className="folder-tree-name">{folder.name}</span>
                <span className="folder-tree-count">{folder.items.length}</span>
              </div>
              {expanded && (
                <div className="folder-tree-children">
                  {folder.items.map((item) => renderConversationItem(item))}
                </div>
              )}
            </div>
          );
        })}
        {treeData.root.map((item) => renderConversationItem(item))}
      </div>
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
        {editing && (
          <div style={{ marginTop: 16 }}>
            <Text strong>成员</Text>
            <Space direction="vertical" style={{ width: "100%", marginTop: 8 }}>
              {(editing.participants ?? [])
                .filter((p) => p.participant_type === "agent")
                .map((p) => (
                  <div
                    key={p.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <Tag>{p.agent_name ?? p.agent_id}</Tag>
                    <Button
                      size="small"
                      danger
                      disabled={
                        (editing.participants ?? []).filter(
                          (x) => x.participant_type === "agent",
                        ).length <= 1
                      }
                      onClick={async () => {
                        if (!p.id) return;
                        try {
                          await api.removeParticipant(
                            editing.id,
                            p.id,
                          );
                          const nextParticipants = (
                            editing.participants ?? []
                          ).filter(
                            (x) =>
                              x.id !== p.id,
                          );
                          const next = { ...editing, participants: nextParticipants };
                          setEditing(next);
                          onEdit(next, { participants: nextParticipants });
                          message.success("成员已移除");
                        } catch (err: any) {
                          if (err?.response?.status === 404) {
                            const nextParticipants = (
                              editing.participants ?? []
                            ).filter(
                              (x) =>
                                x.id !== p.id,
                            );
                            const next = { ...editing, participants: nextParticipants };
                            setEditing(next);
                            onEdit(next, { participants: nextParticipants });
                            message.success("成员已移除");
                          } else {
                            message.error("移除成员失败");
                          }
                        }
                      }}
                    >
                      删除
                    </Button>
                  </div>
                ))}
              <Select
                placeholder="添加成员"
                value={addingAgent ? undefined : null}
                onChange={async (value: string) => {
                  if (!value || !editing) return;
                  try {
                    await api.addParticipants(editing.id, [value]);
                    const agent = agents.find((a) => a.id === value);
                    const nextParticipants = [
                      ...(editing.participants ?? []),
                      {
                        id: value,
                        agent_id: value,
                        agent_name: agent?.name ?? agent?.display_name ?? value,
                        participant_type: "agent" as const,
                      },
                    ];
                    const next = { ...editing, participants: nextParticipants };
                    setEditing(next);
                    onEdit(next, { participants: nextParticipants });
                    message.success("成员已添加");
                    setAddingAgent(false);
                  } catch {
                    message.error("添加成员失败");
                  }
                }}
                options={agents
                  .filter(
                    (a) =>
                      !(editing.participants ?? []).some(
                        (p) => p.agent_id === a.id,
                      ),
                  )
                  .map((a) => ({
                    label: a.display_name ?? a.name,
                    value: a.id,
                  }))}
              />
            </Space>
          </div>
        )}
      </Modal>
        </>
      )}
    </Sider>
  );
}
