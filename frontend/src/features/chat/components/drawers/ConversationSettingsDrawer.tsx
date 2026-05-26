import { useEffect, useMemo } from "react";
import { BranchesOutlined, SaveOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  Space,
  Typography,
} from "antd";
import { mergeConversationCategories } from "../../../../lib/conversation";
import type { Agent, Conversation } from "../../../../types";

const { Text } = Typography;
const { TextArea } = Input;

export function ConversationSettingsDrawer({
  open,
  active,
  categoryOptions,
  onClose,
  onSaveConversation,
  onOpenWorkflow,
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

        <Alert
          type="info"
          showIcon
          message="工作流画布已迁移到独立编排页"
          description="当前群聊的 workflow 仍绑定 conversation.extra.workflow；发送消息时仍按这个会话的画布执行。"
        />
        <Button
          block
          size="large"
          icon={<BranchesOutlined />}
          onClick={onOpenWorkflow}
          disabled={!active || active.chat_type !== "group"}
          data-testid="open-full-workflow"
        >
          打开完整画布
        </Button>
        <Text type="secondary">
          抽屉仅保留命名、分类和备注等基础设置，复杂编排请进入完整工作流页面。
        </Text>
      </Space>
    </Drawer>
  );
}
