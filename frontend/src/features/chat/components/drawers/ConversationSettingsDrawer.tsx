import { useEffect, useMemo } from "react";
import { App as AntApp, Button, Drawer, Form, Input, Select, Space, Tag, Typography } from "antd";
import { mergeConversationCategories } from "@/lib/conversation";
import type { Agent, Conversation } from "@/types";

const { Text } = Typography;
const { TextArea } = Input;

export function ConversationSettingsDrawer({
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
  const { message } = AntApp.useApp();

  const categorySelectOptions = useMemo(
    () =>
      mergeConversationCategories(categoryOptions, [
        active?.folder || active?.category || "Default",
      ]).map((name) => ({ label: name, value: name })),
    [active?.category, active?.folder, categoryOptions],
  );

  const activeAgentIds = new Set(
    active?.participants
      .map((item) => item.agent_id)
      .filter(Boolean) as string[],
  );
  const activeAgents = agents.filter((agent) => activeAgentIds.has(agent.id));

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      title: active?.title,
      group_number: active?.group_number || "",
      folder: active?.folder || active?.category || "Default",
      remark: active?.remark || "",
    });
  }, [active, form, open]);

  const save = async (values: {
    title: string;
    folder: string;
    remark?: string;
  }) => {
    if (!active) return;
    await onSaveConversation(active, {
      title: values.title,
      folder: values.folder,
      category: values.folder,
      remark: values.remark || "",
    });
    message.success("群聊信息已保存");
  };

  return (
    <Drawer title="群聊设置" width={560} open={open} onClose={onClose}>
      <Form form={form} layout="vertical" onFinish={save}>
        <Form.Item
          name="title"
          label="群聊名称"
          rules={[{ required: true, message: "请输入群聊名称" }]}
        >
          <Input maxLength={80} placeholder="请输入群聊名称" />
        </Form.Item>

        {active?.chat_type === "group" && (
          <Form.Item name="group_number" label="群号">
            <Input disabled />
          </Form.Item>
        )}

        <Form.Item name="folder" label="分类/文件夹">
          <Select options={categorySelectOptions} placeholder="选择分类" />
        </Form.Item>

        <Form.Item name="remark" label="备注">
          <TextArea rows={4} maxLength={300} placeholder="记录这个群聊的用途、范围或注意事项" />
        </Form.Item>

        {active?.chat_type === "group" && (
          <div className="conversation-settings-members">
            <Text strong>当前 Agent</Text>
            <Space size={[6, 6]} wrap className="conversation-settings-members-list">
              {activeAgents.length ? (
                activeAgents.map((agent) => (
                  <Tag key={agent.id} color="blue">
                    {agent.name}
                  </Tag>
                ))
              ) : (
                <Text type="secondary">暂无 Agent 成员</Text>
              )}
            </Space>
          </div>
        )}

        <Space>
          <Button type="primary" htmlType="submit" disabled={!active}>
            保存资料
          </Button>
          <Button onClick={onClose}>关闭</Button>
        </Space>
      </Form>
    </Drawer>
  );
}
