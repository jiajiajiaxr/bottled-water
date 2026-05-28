import { useEffect, useMemo } from "react";
import { SaveOutlined } from "@ant-design/icons";
import { Button, Drawer, Form, Input, Select, Space } from "antd";
import { mergeConversationCategories } from "../../../../lib/conversation";
import type { Agent, Conversation } from "../../../../types";

const { TextArea } = Input;

export function ConversationSettingsDrawer({
  open,
  active,
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
  onOpenWorkflow?: () => void;
}) {
  const [form] = Form.useForm();
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

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      title: active?.title,
      folder: active?.folder || active?.category || "Default",
      remark: active?.remark || "",
    });
  }, [active, form, open]);

  return (
    <Drawer title="群聊设置" width={560} open={open} onClose={onClose}>
      <Space direction="vertical" size={16} className="full-width">
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
          }}
        >
          <Form.Item name="title" label="群聊名称" rules={[{ required: true }]}>
            <Input maxLength={80} />
          </Form.Item>
          <Form.Item name="folder" label="分类 / 文件夹">
            <Select options={conversationCategoryOptions} placeholder="选择分类" />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <TextArea rows={4} maxLength={300} />
          </Form.Item>
          <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>
            保存基础信息
          </Button>
        </Form>
      </Space>
    </Drawer>
  );
}
