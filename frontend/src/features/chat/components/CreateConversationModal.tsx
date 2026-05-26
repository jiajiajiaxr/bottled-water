import { useEffect, useRef } from "react";
import { Checkbox, Form, Input, Modal, Select } from "antd";
import { normalizeConversationCategory } from "@/lib/conversation";
import type { Agent } from "@/types";

export function CreateConversationModal({
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
